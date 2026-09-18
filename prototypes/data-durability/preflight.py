"""PROTOTYPE — cold-start refusal through real manifest/model preflight, no decoder."""
import json
from dataclasses import replace
from pathlib import Path
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig,build_live_runtime_factory
from probe import SCRATCH,OUT
manifest=Path.home()/'.local/share/moss-transcribe-diarize/live/live-provider-manifest.json'
r={}
for name,path in [('missing',SCRATCH/'no-manifest.json'),('invalid',SCRATCH/'invalid-manifest.json')]:
    if name=='invalid':path.write_text('{')
    try:LiveProviderBundleConfig.from_manifest(path)
    except Exception as e:r[name]={'type':type(e).__name__,'code':e.failure.code,'content_free_reason':str(e).replace(str(path),'<private manifest path>')}
c=LiveProviderBundleConfig.from_manifest(manifest);p=c.preflight()
r['valid']={'available':p.available,'failure_count':len(p.failures)}
# Missing actual ONNX asset: exercise the bundle's model-artifact preflight.
missing=replace(c.assets[0],path=SCRATCH/'missing-model.onnx')
bad=replace(c,assets=(missing,)+c.assets[1:])
try:build_live_runtime_factory(bad,object())
except Exception as e:r['missing_model']={'type':type(e).__name__,'code':e.failure.code,'reason':str(e),'failure_count':len((e.failure.detail or {}).get('failures',[]))}
(OUT/'preflight.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
