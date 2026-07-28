# Shared discipline for the tracked server-side live deployment tools.
#
# Sourced, never executed. This is the same output contract the Mac packaging tools follow
# (`macos/scripts/moss-tool-lib.sh`), kept as a separate file on purpose: the two host families
# share the *vocabulary* but none of the primitives. The Mac side needs `codesign`, `shasum`,
# `ditto` and the keychain; the server side needs `openssl`, `curl` and POSIX modes. A test
# asserts the two libraries emit byte-identical lines for the same call, so the vocabulary
# cannot drift apart.
#
#   * `--dry-run` prints the ordered plan plus the rollback command and changes nothing,
#     so a reviewer can read exactly what a real run would do.
#   * the `rollback:` line is printed *before* the first mutation, never after it.
#   * re-running with the same inputs prints `unchanged:` and mutates nothing. On this side
#     that is a safety property, not tidiness: regenerating TLS material changes the pin, and
#     every already-paired Mac client pins the exact leaf certificate.
#
# Output is line-oriented so acceptance tests can read it without parsing prose:
#
#   plan: <ordered step>          what a real run will do
#   rollback: <command>           the exact command that undoes the mutation
#   change: <what moved>          a mutation that happened
#   unchanged: <why>              a mutation that was correctly skipped
#   evidence: <key>=<value>       observed facts, safe to log (never a secret)
#   error: <message>              on stderr, immediately before a non-zero exit
#
# A secret never travels on any of those lines. The one tool that handles a secret
# (`live-pair.sh`) prints it on its own `payload:` line and says so.

MOSS_TOOL_DRY_RUN="${MOSS_TOOL_DRY_RUN:-0}"

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

plan() { printf 'plan: %s\n' "$*"; }
rollback() { printf 'rollback: %s\n' "$*"; }
change() { printf 'change: %s\n' "$*"; }
unchanged() { printf 'unchanged: %s\n' "$*"; }
evidence() { printf 'evidence: %s=%s\n' "$1" "$2"; }

dry_run() { [ "$MOSS_TOOL_DRY_RUN" = "1" ]; }

require_cmd() {
    for candidate in "$@"; do
        command -v "$candidate" >/dev/null 2>&1 || die "required tool not found on PATH: $candidate"
    done
}

utc_stamp() { date -u +%Y%m%dT%H%M%SZ; }

# The digest form the Mac client pins and the one the live server computes for itself
# (`web_cli._certificate_sha256`): SHA-256 over the leaf certificate's DER bytes, lowercase
# hex, no separators. `openssl dgst` labels its output differently across versions, hence
# `$NF`; `x509 -fingerprint` is a second opinion on the same bytes, checked by the caller.
certificate_pin() {
    local cert="$1"
    [ -f "$cert" ] || die "cannot pin a missing certificate: $cert"
    openssl x509 -in "$cert" -outform DER 2>/dev/null |
        openssl dgst -sha256 | awk '{print $NF}' | tr 'A-Z' 'a-z'
}

# `SHA256 Fingerprint=AB:CD:...` -> `abcd...`, so the operator can read the pin off either
# command and get the same 64 characters the client will accept.
certificate_fingerprint_pin() {
    local cert="$1"
    [ -f "$cert" ] || die "cannot fingerprint a missing certificate: $cert"
    openssl x509 -in "$cert" -noout -fingerprint -sha256 2>/dev/null |
        sed -e 's/^.*=//' -e 's/://g' | tr -d '[:space:]' | tr 'A-Z' 'a-z'
}

# The subject alternative names actually in a certificate, one per line, in the
# `DNS:name` / `IP:address` spelling this tool family uses on both input and output.
# Parsed out of `-text` on purpose: `x509 -ext` is unavailable in LibreSSL, and an
# operator's PATH decides which openssl a deployment step gets.
certificate_sans() {
    local cert="$1"
    [ -f "$cert" ] || die "cannot read names from a missing certificate: $cert"
    openssl x509 -in "$cert" -noout -text 2>/dev/null |
        awk '
            /X509v3 Subject Alternative Name/ { capture = 1; next }
            capture {
                gsub(/^[[:space:]]+|[[:space:]]+$/, "")
                gsub(/[[:space:]]*,[[:space:]]*/, "\n")
                print
                exit
            }
        ' |
        sed -e 's/^IP Address:/IP:/' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' |
        grep -v '^$' || true
}

# The public key a certificate carries and the public key a private key implies, in the same
# SPKI PEM spelling, so an installed pair can be proven to belong together without assuming
# the key algorithm.
certificate_public_key() {
    openssl x509 -in "$1" -noout -pubkey 2>/dev/null
}

private_key_public_key() {
    openssl pkey -in "$1" -pubout 2>/dev/null
}

file_mode() {
    local target="$1"
    [ -e "$target" ] || die "cannot read the mode of a missing path: $target"
    if stat -c '%a' "$target" >/dev/null 2>&1; then
        stat -c '%a' "$target"
    else
        stat -f '%Lp' "$target"
    fi
}

# IPv4 only, and only inside the networks live access admits at all (`live_auth`'s
# `_ALLOWED_PEER_NETWORKS`: loopback, RFC1918, and the CGNAT range Tailscale hands out).
# Narrower than the server on purpose — a certificate name this refuses can still be added
# deliberately, but a name the *server* would refuse must never end up in the material a
# deployment step installs. IPv6 literals are refused rather than guessed at.
private_live_ipv4() {
    local value="$1" first second third fourth
    case "$value" in
        *[!0-9.]*) return 1 ;;
    esac
    IFS=. read -r first second third fourth <<EOF
$value
EOF
    for octet in "$first" "$second" "$third" "$fourth"; do
        [ -n "$octet" ] || return 1
        case "$octet" in
            0 | [1-9] | [1-9][0-9] | 1[0-9][0-9] | 2[0-4][0-9] | 25[0-5]) ;;
            *) return 1 ;;
        esac
    done
    case "$first" in
        127) return 0 ;;
        10) return 0 ;;
        192) [ "$second" = "168" ] && return 0 ;;
        172) [ "$second" -ge 16 ] && [ "$second" -le 31 ] && return 0 ;;
        100) [ "$second" -ge 64 ] && [ "$second" -le 127 ] && return 0 ;;
    esac
    return 1
}

# A DNS name a browser can match: dot-separated labels of letters, digits and inner hyphens,
# with a final label that is not all digits. That last rule is what separates a name from an
# address written into the wrong flag: `10.0.0.5` is label-legal but can only ever be an
# address, and as a DNS-type certificate name it would match nothing.
valid_dns_name() {
    local value="$1" label rest
    [ -n "$value" ] || return 1
    [ "${#value}" -le 253 ] || return 1
    case "$value" in
        .* | *. | *..*) return 1 ;;
    esac
    rest="$value"
    label=""
    while [ -n "$rest" ]; do
        label="${rest%%.*}"
        if [ "$label" = "$rest" ]; then
            rest=""
        else
            rest="${rest#*.}"
        fi
        [ -n "$label" ] || return 1
        [ "${#label}" -le 63 ] || return 1
        case "$label" in
            -* | *-) return 1 ;;
            *[!a-zA-Z0-9-]*) return 1 ;;
        esac
    done
    case "$label" in
        *[!0-9]*) return 0 ;;
    esac
    return 1
}

# True when a value can only have been meant as an address, so a tool can say which flag to
# use instead of only reporting that it is not a name.
address_like() {
    case "$1" in
        "" | *[!0-9a-fA-F.:]*) return 1 ;;
        *.* | *:*) return 0 ;;
    esac
    return 1
}
