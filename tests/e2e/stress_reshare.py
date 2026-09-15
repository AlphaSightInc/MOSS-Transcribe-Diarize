"""Mid-session reshare / device switch at the wire contract.

replaceLane() bumps the lane's device_epoch and flags the next frame discontinuous.
Nothing has ever checked the server accepts that mid-capture and keeps transcribing.
"""
import base64, json, ssl, time, urllib.request, urllib.error, wave
from pathlib import Path
import os
BASE=os.environ.get("MOSS_BASE","https://127.0.0.1:17861"); CTX=ssl._create_unverified_context()
ROOT=Path(__file__).resolve().parents[2]
WAV=ROOT/"evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s/audio.wav"
jar={}
def call(m,p,b=None,timeout=60):
    d=json.dumps(b).encode() if b is not None else None
    h={"Content-Type":"application/json"}
    if jar: h["Cookie"]="; ".join(f"{k}={v}" for k,v in jar.items())
    r=urllib.request.Request(BASE+p,data=d,method=m,headers=h)
    try:
        with urllib.request.urlopen(r,context=CTX,timeout=timeout) as resp:
            for hh in resp.headers.get_all("Set-Cookie") or []:
                k,_,v=hh.partition("="); jar[k]=v.split(";")[0]
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, e.read()[:200].decode(errors="replace")

results=[]
def check(n, ok, d=""):
    results.append(ok); print(f"  {'PASS' if ok else 'FAIL'}  {n}{(' | '+str(d)[:120]) if d else ''}")

call("POST","/api/workspace/bootstrap")
_,desc=call("GET","/api/live/descriptor"); desc=desc["descriptor"]
fs,rate=desc["frame_samples"],desc["sample_rate"]
_,created=call("POST","/api/live/sessions",{"source_revision":desc["source_revision"]})
sid=created["id"]
with wave.open(str(WAV)) as w: pcm=w.readframes(min(w.getnframes(), rate*30))
fb=fs*2; silence=b"\0"*fb
epoch={"system":int(time.time()*1e9),"microphone":int(time.time()*1e9)}
disc={"system":False,"microphone":False}
errors=[]

def send(lane, seq, chunk):
    s,b=call("POST",f"/api/live/sessions/{sid}/frames",{
        "lane":lane,"sequence":seq,"capture_timestamp_ns":epoch[lane]+seq*int(fs/rate*1e9),
        "device_epoch":epoch[lane],"pcm_base64":base64.b64encode(chunk).decode(),
        "sample_count":fs,"sample_rate":rate,"silent":chunk==silence,
        "discontinuity":disc[lane]})
    if disc[lane]: disc[lane]=False
    if s!=200: errors.append((lane,seq,s,str(b)[:90]))
    return s

total=40; reshare_at=14; micswitch_at=26
t0=time.monotonic()
for seq in range(total):
    off=seq*fb
    if seq==reshare_at:
        # the operator picks a different tab: new device, new epoch, discontinuous
        epoch["system"]+=1_000_000; disc["system"]=True
        print(f"  -- reshared SYSTEM lane at frame {seq} (device_epoch bumped, discontinuity set)")
    if seq==micswitch_at:
        epoch["microphone"]+=1_000_000; disc["microphone"]=True
        print(f"  -- switched MICROPHONE device at frame {seq}")
    send("system", seq, pcm[off:off+fb] or silence)
    send("microphone", seq, silence)
    time.sleep(max(0.0,(seq+1)*(fs/rate)-(time.monotonic()-t0)))

check("every frame accepted across both mid-session swaps", not errors, f"{errors[:3]}")
s,_=call("POST",f"/api/live/sessions/{sid}/stop",{"deadline":30})
check("session stops cleanly after the swaps", s==200, f"status={s}")
time.sleep(12)
s,snap=call("GET",f"/api/live/sessions/{sid}/snapshot")
sess=snap.get("snapshot",{}).get("session",{})
segs=sess.get("effective_transcript") or sess.get("committed") or []
if isinstance(segs,dict): segs=segs.get("segments") or []
words=sum(len(str(x.get("text","")).split()) for x in segs)
last=max([x.get("end_sample",0) for x in segs], default=0)
check("finalizes after the swaps", sess.get("finalization_status")=="final", sess.get("finalization_status"))
check("transcribes across the reshare boundary",
      last > reshare_at*fs, f"last_sample={last} reshare_sample={reshare_at*fs}")
check("transcribes across the mic-switch boundary",
      last > micswitch_at*fs, f"last_sample={last} switch_sample={micswitch_at*fs}")
check("produced real text", words>20, f"{words} words in {len(segs)} segments")
print(f"\n  {len(results)-results.count(False)}/{len(results)} reshare checks passed")
for x in segs[:6]: print(f"    [{x.get('start_sample')}] {x.get('canonical_speaker')}: {str(x.get('text',''))[:70]}")
raise SystemExit(1 if results.count(False) else 0)
