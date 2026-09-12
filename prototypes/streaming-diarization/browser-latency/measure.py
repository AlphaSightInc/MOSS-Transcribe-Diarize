"""Run E2E row 4 with content-free capture/render timing; preserve the local database."""
import argparse,asyncio,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('workspace_e2e',ROOT/'tests/e2e/verify_workspace.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class TimedHarness(m.Harness):
    async def open(self):
        if not getattr(self,'timing_installed',False):
            self.timing_installed=True
            await self.context.add_init_script(path=str(Path(__file__).with_name('instrument.js')))
            await self.page.route('**/static/app.js',lambda route:route.fulfill(path=str(Path(self.args.bundle).resolve()),content_type='application/javascript'))
        await super().open()

    async def live(self):
        if self.args.known_onset is None:
            result=await super().live()
        else:
            await self.setup_live(); ident=await self.start_live('live')
            await self.page.locator('.utt-text').first.wait_for(timeout=35000)
            first=m.time.monotonic()-self.started
            await asyncio.sleep(max(0,10-(m.time.monotonic()-self.started)))
            await self.page.get_by_role('button',name='Stop and finalize',exact=True).click()
            terminal=await self.terminal(ident,240)
            result={'ok':terminal['status']=='completed','first_visible_seconds':first,
                    'known_file_onset_seconds':self.args.known_onset,'meeting':ident}
        timings=await self.page.evaluate('window.__mossTimings')
        (self.out/'timings.json').write_text(json.dumps(timings,indent=2)+'\n')
        # Audio stays in memory for alignment; only offsets/correlation enter evidence.
        audio=await self.page.evaluate('window.__mossCalibration')
        import numpy as np, soundfile as sf
        from scipy.signal import correlate
        reference,rate=sf.read(self.wav)
        alignment=[]
        for row in audio:
            sample=np.asarray(row['samples'])
            corr=correlate(reference,sample,mode='valid',method='fft')
            offset=int(np.argmax(corr));part=reference[offset:offset+len(sample)]
            score=float(np.dot(part,sample)/(np.linalg.norm(part)*np.linalg.norm(sample)+1e-15))
            alignment.append(dict(lane=row['lane'],startFrame=row['startFrame'],file_offset_samples=offset,correlation=score))
        (self.out/'alignment.json').write_text(json.dumps(alignment,indent=2)+'\n')
        return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--base',default='https://127.0.0.1:17861');p.add_argument('--corpus',required=True);p.add_argument('--output',required=True);p.add_argument('--bundle',required=True);p.add_argument('--known-onset',type=float)
 args=p.parse_args();args.rows='4';args.new_workspace=False
 raise SystemExit(asyncio.run(TimedHarness(args).run()))
