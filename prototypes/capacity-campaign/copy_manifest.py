"""PROTOTYPE: prepare the user-authorized 30-minute local measurement copy only."""
import json
from pathlib import Path

from moss_transcribe_diarize.app.live_manifest_finalizer import (
    LiveIdentityRecalibration, LiveManifestRetune, finalize_payload, verify_admission,
)

source = Path.home()/'.local/share/moss-transcribe-diarize/live/live-provider-manifest.json'
destination = Path('.wp6-tmp/manifest-30m.json')
original = source.read_bytes()
payload = json.loads(original)
# Copying to another directory must preserve what the relative assets refer to.
for asset in [*payload['assets'], payload['golden']['input']]:
    asset['path'] = str((source.parent/asset['path']).resolve())
bounds, identity, provider = payload['bounds_config'], payload['identity_config'], payload['identity_provider']
final, contract = finalize_payload(
    payload, source_revision=payload['source_revision'],
    retune=LiveManifestRetune(hard_cap_samples=bounds['hard_cap_samples'],
        max_retained_samples=bounds['max_retained_samples'], frame_samples=bounds['frame_samples'],
        max_tape_bytes=57_600_000),
    identity=LiveIdentityRecalibration(min_match_score=identity['min_match_score'],
        min_match_margin=identity['min_match_margin'], album_admission_seconds=provider['album_admission_seconds'],
        birth_min_seconds=provider['birth_min_seconds']),
)
admission = verify_admission(final, base_dir=destination.parent)
destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(final, indent=2)+'\n')
destination.chmod(0o600)
(destination.parent/'manifest-original.json').write_bytes(original)
(destination.parent/'manifest-original.json').chmod(0o600)
assert source.read_bytes() == original
print(json.dumps(dict(source=str(source), source_mtime_ns=source.stat().st_mtime_ns,
    destination=str(destination), before_bounds=bounds, after_bounds=final['bounds_config'],
    contract=contract, admission=admission, shared_source_unchanged=True), indent=2))
