#!/usr/bin/env bash
# Run only after the final candidate and trusted TLS are qualified and admitted.
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
linux_user_dir="$(getent passwd "$(id -un)" | cut -d: -f6)"
runtime_root="${linux_user_dir}/.local/share/moss-transcribe-diarize"
unit_dir="${linux_user_dir}/.config/systemd/user"
systemctl --user is-active --quiet moss-web.service
case "$(systemctl --user show moss-web.service --property=ExecReload --value)" in
  *'kill -HUP'*) ;;
  *) echo 'Qualified non-interrupting web reload required before enabling renewal.' >&2; exit 1 ;;
esac
bash "${script_dir}/manage-certificate.sh" --check
install -d -m 0700 "${runtime_root}/certificate-ops"
install -m 0500 "${script_dir}/manage-certificate.sh" "${runtime_root}/certificate-ops/manage-certificate.sh"
install -m 0644 "${script_dir}/systemd/moss-certificate-renew.service" "${unit_dir}/moss-certificate-renew.service"
install -m 0644 "${script_dir}/systemd/moss-certificate-renew.timer" "${unit_dir}/moss-certificate-renew.timer"
systemctl --user daemon-reload
systemctl --user start moss-certificate-renew.service
systemctl --user enable --now moss-certificate-renew.timer
