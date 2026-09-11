#!/usr/bin/env bash
# DNS-01 only. Never opens an inbound port, installs client trust, or restarts MOSS.
set -euo pipefail
umask 077
mode="${1:---check}"
case "${mode}" in --check|--staging|--issue|--renew) ;; *) echo 'usage: manage-certificate.sh --check|--staging|--issue|--renew' >&2; exit 2 ;; esac
linux_user_dir="$(getent passwd "$(id -un)" | cut -d: -f6)"
config_dir="${linux_user_dir}/.config/moss-transcribe-diarize"
runtime_root="${linux_user_dir}/.local/share/moss-transcribe-diarize"
lego_binary="${linux_user_dir}/.local/bin/lego"
hostname=ga0-alienware-rtx4070ti.tailnet.aisight.us
credential="${config_dir}/netlify-token"
profile="${config_dir}/certificate.env"
for private_file in "${credential}" "${profile}"; do
  [ -s "${private_file}" ] && [ "$(stat -c '%a' "${private_file}")" = 600 ] || { echo "Missing/non-private certificate prerequisite: ${private_file}" >&2; exit 1; }
done
# This profile holds only the ACME contact address, never the DNS key.
. "${profile}"
: "${MOSS_ACME_EMAIL:?Set MOSS_ACME_EMAIL in the private certificate.env file}"
[ -x "${lego_binary}" ] || { echo 'lego is not installed' >&2; exit 1; }
case "$("${lego_binary}" --version)" in 'lego version 5.'*) ;; *) echo 'lego v5 required' >&2; exit 1 ;; esac
unset NETLIFY_TOKEN
export NETLIFY_TOKEN_FILE="${credential}"
if [ "${mode}" = --check ]; then
  echo 'Certificate prerequisites present; no DNS request or service change performed.'
  exit 0
fi
mkdir -p "${runtime_root}/acme"
# One issuance/renewal at a time, including manual invocations and the timer.
exec 9>"${runtime_root}/acme/operation.lock"
flock -n 9 || { echo 'Another certificate operation is running' >&2; exit 1; }
certificate_root="${runtime_root}/acme/production"
server=letsencrypt
if [ "${mode}" = --staging ]; then
  certificate_root="${runtime_root}/acme/staging"
  server=letsencrypt-staging
fi
mkdir -p "${certificate_root}"
certificate="${certificate_root}/certificates/${hostname}.crt"
if [ "${mode}" = --renew ] && [ ! -s "${certificate}" ]; then
  echo 'Issue and qualify the production certificate before enabling renewal.' >&2; exit 1
fi
# The host resolves the capture hostname through Headscale MagicDNS, which answers SOA
# queries with NOTIMP. Public resolvers are required for apex determination against the
# real aisight.us zone; without them lego cannot find the zone to write the TXT record.
# lego v5: run handles both issuance and due renewal; do not force needless renewal.
"${lego_binary}" run --accept-tos --email "${MOSS_ACME_EMAIL}" --domains "${hostname}" \
  --dns netlify --dns.resolvers 1.1.1.1:53,8.8.8.8:53 \
  --server "${server}" --path "${certificate_root}" --no-random-sleep
chmod 0600 "${certificate_root}/certificates/${hostname}.key"
if [ "${mode}" != --renew ]; then
  echo "Certificate operation complete: ${certificate}; no service changed."
  exit 0
fi
# Reload only a running unit that explicitly supports the non-interrupting HUP path.
if ! systemctl --user is-active --quiet moss-web.service; then
  echo 'Certificate renewed/on schedule; web inactive, next startup will read it.'
  exit 0
fi
case "$(systemctl --user show moss-web.service --property=ExecReload --value)" in
  *'kill -HUP'*) ;;
  *) echo 'Certificate saved; running web lacks the qualified reload action. No signal sent.' >&2; exit 1 ;;
esac
systemctl --user reload moss-web.service
expected="$(openssl x509 -in "${certificate}" -noout -serial)"
for attempt in {1..10}; do
  served="$(timeout 10 openssl s_client -connect 127.0.0.1:7861 -servername "${hostname}" \
    -verify_hostname "${hostname}" -verify_return_error -CApath /etc/ssl/certs </dev/null 2>/dev/null | openssl x509 -noout -serial)" || served=''
  if [ "${served}" = "${expected}" ]; then
    echo 'Trusted renewed certificate served; no process restart.'; exit 0
  fi
  sleep 1
done
echo 'Certificate saved but served identity was not confirmed; inspect journal. No restart attempted.' >&2
exit 1
