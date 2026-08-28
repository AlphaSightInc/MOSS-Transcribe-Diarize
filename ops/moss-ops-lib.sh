# Shared output and dry-run primitives for the Account deployment tools.
# Sourced, never executed. Plan and rollback lines precede mutation; evidence is content-free,
# and no secret is printed.

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
