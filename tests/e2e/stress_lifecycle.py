"""Live-session lifecycle stress: the §6 cases verify_workspace.py does not cover.

start/stop/restart, double-stop, frames-after-stop, stop with no audio, concurrent
sessions, snapshot-after-stop (the reload/reattach path's server half).
"""
import base64, json, os, ssl, time, urllib.request, urllib.error, wave
from pathlib import Path

BASE=os.environ.get("MOSS_BASE","https://127.0.0.1:17861"); CTX=ssl._create_unverified_context()
ROOT=Path(__file__).resolve().parents[2]
WAV=ROOT/"evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s/audio.wav"

class C:
    def __init__(self): self.jar={}
    def __call__(self, m, p, b=None, timeout=60):
        d=json.dumps(b).encode() if b is not None else None
        h={"Content-Type":"application/json"}
        if self.jar: h["Cookie"]="; ".join(f"{k}={v}" for k,v in self.jar.items())
        r=urllib.request.Request(BASE+p,data=d,method=m,headers=h)
        try:
            with urllib.request.urlopen(r,context=CTX,timeout=timeout) as resp:
                for hh in resp.headers.get_all("Set-Cookie") or []:
                    k,_,v=hh.partition("="); self.jar[k]=v.split(";")[0]
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, e.read()[:160].decode(errors="replace")
        except Exception as e:
            return "EXC", f"{type(e).__name__}: {e}"

results=[]
def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{(' | '+str(detail)[:110]) if detail else ''}")

c=C(); c("POST","/api/workspace/bootstrap")
s,desc=c("GET","/api/live/descriptor"); desc=desc["descriptor"]
fs,rate=desc["frame_samples"],desc["sample_rate"]; rev=desc["source_revision"]
with wave.open(str(WAV)) as w: pcm=w.readframes(min(w.getnframes(), rate*8))
frame_bytes=fs*2

def new_session():
    s,b=c("POST","/api/live/sessions",{"source_revision":rev}); return b.get("id") if isinstance(b,dict) else None

def send(sid, seq, chunk, lane="system", epoch=None):
    if lane=='system':
        health=dict(state='capturing',device_epoch=epoch or 0,dropped_frames=0,discontinuities=0,failure_code=None)
        c('POST',f'/api/live/sessions/{sid}/heartbeat',dict(
            schema='moss-live-helper-health.v1',instance_id='lifecycle-stress',sequence=seq,
            sent_monotonic_ns=time.monotonic_ns(),helper_version='e2e',state='capturing',
            lanes={'system':health,'microphone':dict(health)}))
    return c("POST",f"/api/live/sessions/{sid}/frames",{
        "lane":lane,"sequence":seq,"capture_timestamp_ns":(epoch or 0)+seq*int(fs/rate*1e9),
        "device_epoch":epoch or 0,"pcm_base64":base64.b64encode(chunk).decode(),
        "sample_count":fs,"sample_rate":rate,"silent":False,"discontinuity":False})

def feed(sid, frames=4):
    ep=int(time.time()*1e9); silence=b"\0"*frame_bytes
    for seq in range(frames):
        off=seq*frame_bytes
        send(sid,seq,pcm[off:off+frame_bytes] or silence,"system",ep)
        send(sid,seq,silence,"microphone",ep)
    return ep

print("\n=== 1. start -> stop -> restart (new session in same workspace) ===")
a=new_session(); feed(a); s1,_=c("POST",f"/api/live/sessions/{a}/stop",{"deadline":30})
b=new_session(); feed(b); s2,_=c("POST",f"/api/live/sessions/{b}/stop",{"deadline":30})
check("restart after stop yields a usable second session", bool(a) and bool(b) and a!=b and s1==200 and s2==200, f"stop1={s1} stop2={s2}")

print("\n=== 2. Stop pressed twice quickly ===")
d=new_session(); feed(d)
r1=c("POST",f"/api/live/sessions/{d}/stop",{"deadline":30})
r2=c("POST",f"/api/live/sessions/{d}/stop",{"deadline":30})
check("double stop does not 5xx", not (isinstance(r2[0],int) and r2[0]>=500), f"first={r1[0]} second={r2[0]} body={str(r2[1])[:80]}")

print("\n=== 3. frames after stop are refused ===")
late=send(d, 99, pcm[:frame_bytes], "system", int(time.time()*1e9))
check("frame after stop is refused (4xx, not accepted, not 5xx)",
      isinstance(late[0],int) and 400<=late[0]<500, f"status={late[0]} body={str(late[1])[:80]}")

print("\n=== 4. stop a session that received no audio at all ===")
e=new_session(); r=c("POST",f"/api/live/sessions/{e}/stop",{"deadline":30})
check("empty session stops without 5xx", not (isinstance(r[0],int) and r[0]>=500), f"status={r[0]} body={str(r[1])[:80]}")

print("\n=== 5. snapshot after stop (the reload / reattach path) ===")
time.sleep(8)
s,snap=c("GET",f"/api/live/sessions/{a}/snapshot")
sess=(snap or {}).get("snapshot",{}).get("session",{}) if isinstance(snap,dict) else {}
check("snapshot after stop still serves the finalized session", s==200 and bool(sess), f"status={s} finalization={sess.get('finalization_status')}")

print("\n=== 6. two concurrent live sessions in one workspace ===")
g=new_session(); h=new_session()
ok = bool(g) and bool(h)
if ok:
    ep=int(time.time()*1e9)
    rg=send(g,0,pcm[:frame_bytes],"system",ep); rh=send(h,0,pcm[:frame_bytes],"system",ep)
    ok = rg[0]==200 and rh[0]==200
    for x in (g,h): c("POST",f"/api/live/sessions/{x}/stop",{"deadline":30})
check("two concurrent sessions both accept frames", ok, f"g={g and g[:8]} h={h and h[:8]}")

print("\n=== 7. unknown session id ===")
s,_=c("GET","/api/live/sessions/does-not-exist-000000/snapshot")
check("unknown session id is 404", s==404, f"status={s}")

bad=sum(1 for _,ok,_ in results if not ok)
print(f"\n  {len(results)-bad}/{len(results)} lifecycle checks passed")
raise SystemExit(1 if bad else 0)
