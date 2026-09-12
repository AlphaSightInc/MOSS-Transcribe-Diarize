"""Temporary timing hooks. Restore sources and shipped assets even if the build fails."""
from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parents[3]
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
files=['frontend/src/capture/captureClient.ts','frontend/src/state/session.ts',
       'moss_transcribe_diarize/app/frontend_assets/app.js',
       'moss_transcribe_diarize/app/frontend_assets/app.js.map',
       'moss_transcribe_diarize/app/frontend_assets/styles.css']
saved={p:(root/p).read_bytes() for p in files}
try:
 p=root/files[0];s=p.read_text().replace('    const level = rms(workletFrame.samples);', '''    (globalThis as any).__mossTiming?.("worklet", {lane, startFrame: workletFrame.startFrame,
      samples: workletFrame.samples.length, sampleRate: this.context?.sampleRate,
      contextTime: this.context?.currentTime, timestamp: this.context?.getOutputTimestamp(),
      session: Boolean(this.session)}, workletFrame.samples);
    const level = rms(workletFrame.samples);''')
 s=s.replace('        const frame = makeV2Frame(', '        const encodeStart = performance.now();\n        const frame = makeV2Frame(')
 s=s.replace('        const result = await this.postFrame(frame, state);', '''        (globalThis as any).__mossTiming?.("encoded", {lane: frame.lane, sequence: frame.sequence,
          startFrame: workletFrame.startFrame, elapsed: performance.now() - encodeStart});
        const result = await this.postFrame(frame, state);''');p.write_text(s)
 p=root/files[1];s=p.read_text().replace('  sessionTranscriptItems.value = upsertTranscriptItems([], items);', '''  (globalThis as any).__mossTiming?.("signal", {items: items.length});
  sessionTranscriptItems.value = upsertTranscriptItems([], items);''');p.write_text(s)
 subprocess.run(['npm','--prefix','frontend','run','build'],cwd=root,check=True,stdout=subprocess.DEVNULL)
 (out/'app.js').write_bytes((root/files[2]).read_bytes())
finally:
 for name,data in saved.items():(root/name).write_bytes(data)
