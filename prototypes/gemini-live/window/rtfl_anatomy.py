"""PROTOTYPE — interval anatomy of cached and fresh RTFL whole-clip responses.

Run after variance_probe.py:
  PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
      prototypes/gemini-live/window/rtfl_anatomy.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
sys.path.insert(0, str(HERE.parent / "harness"))
import gemini_common as gc  # noqa: E402
from corpus import clips  # noqa: E402
from h1_offline import score_case  # noqa: E402
from score import score  # noqa: E402
from moss_transcribe_diarize.evaluation import Segment, calculate_diarization  # noqa: E402
from final_policy import pcm, voiced_mask, words  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P53")
OUTPUT = EVIDENCE / "rtfl-variance-anatomy.json"
CASE = "discussion_rtfl_90s"
DURATION = 90.0


def seconds(rows):
    if not rows:
        return 0.0
    ordered = sorted((x["start"], x["end"]) for x in rows)
    s, e = ordered[0]
    total = 0.0
    for a, b in ordered[1:]:
        if a <= e:
            e = max(e, b)
        else:
            total += e-s
            s, e = a, b
    return total+e-s


def analyze(name, clip_words, ref, mask):
    hyp = gc.words_to_segments(clip_words)
    scored = score(ref, hyp, with_text=False)
    production = calculate_diarization([Segment(**x) for x in ref], [Segment(**x) for x in hyp])
    h1 = score_case(CASE, immediate=[], settled=[], final=hyp)["metrics"]["final"]
    assert abs(scored["der"]-h1["der"]) <= 1e-6
    mapping = production["speaker_mapping"]
    boundaries = sorted({0.0, DURATION, *[v for x in ref+hyp for v in (x["start"], x["end"])],
                         *[max(0.0,min(DURATION,v+offset)) for x in ref for v in (x["start"],x["end"])
                           for offset in (-1.0,-.5,-.25,.25,.5,1.0)],30.0,60.0})
    ref_edges = [v for x in ref for v in (x["start"],x["end"])]
    total = defaultdict(float)
    bins = defaultdict(lambda: defaultdict(float))
    near = {"0.25":defaultdict(float),"0.5":defaultdict(float),"1.0":defaultdict(float)}
    wrong_pairs = defaultdict(float)
    errors = {"miss":[],"false_alarm":[],"confusion":[]}
    fa_voiced = fa_frames = 0.0
    for a,b in zip(boundaries,boundaries[1:]):
        if b-a <= 1e-9: continue
        mid=(a+b)/2
        refs=[r for r in ref if r["start"]<=mid<r["end"]]
        hyps=[h for h in hyp if h["start"]<=mid<h["end"]]
        pairs=[(r,h) for r in refs for h in hyps]
        piece={"reference":len(refs)*(b-a),"hypothesis":len(hyps)*(b-a),
               "miss":(len(refs)-len(pairs))*(b-a),
               "false_alarm":(len(hyps)-len(pairs))*(b-a),
               "confusion":sum(mapping.get(r["speaker"])!=h["speaker"] for r,h in pairs)*(b-a),
               "reference_overlap":(len(refs)>1)*(b-a),
               "hypothesis_overlap":(len(hyps)>1)*(b-a)}
        for k,v in piece.items():
            total[k]+=v
            bins[f"{int(mid//30)*30:02d}-{int(mid//30)*30+30:02d}"][k]+=v
            for width,collector in near.items():
                if min(abs(mid-edge) for edge in ref_edges)<=float(width):collector[k]+=v
        for r,h in pairs:
            if mapping.get(r["speaker"])!=h["speaker"]:
                wrong_pairs[f"{r['speaker']}|{h['speaker']}"]+=b-a
        for kind in errors:
            if piece[kind]>0:
                errors[kind].append({"start":a,"end":b,"seconds":piece[kind],
                                     "reference_speakers":[r["speaker"] for r in refs],
                                     "hypothesis_speakers":[h["speaker"] for h in hyps]})
        if piece["false_alarm"]>0:
            lo=max(0,int(a*100));hi=min(len(mask),int(b*100))
            fa_frames+=max(0,hi-lo)
            fa_voiced+=int(np.sum(mask[lo:hi]))
    # RTFL has no reference or hypothesis overlap under this scorer, so local
    # component pieces should reproduce its global max-clamped arithmetic.
    ref_duration=sum(r["end"]-r["start"] for r in ref)
    assert all(abs(total[k]/ref_duration-scored[k if k!="confusion" else "speaker_confusion"])<2e-5
               for k in ("miss","false_alarm","confusion"))
    top={k:sorted(v,key=lambda x:x["seconds"],reverse=True)[:12] for k,v in errors.items()}
    runs = {}
    for kind, atoms in errors.items():
        joined = []
        for atom in sorted(atoms, key=lambda x: x["start"]):
            same = (joined and abs(joined[-1]["end"]-atom["start"])<1e-8
                    and joined[-1]["reference_speakers"]==atom["reference_speakers"]
                    and joined[-1]["hypothesis_speakers"]==atom["hypothesis_speakers"])
            if same:
                joined[-1]["end"] = atom["end"]
                joined[-1]["seconds"] += atom["seconds"]
            else:
                joined.append(dict(atom))
        runs[kind] = sorted(joined, key=lambda x: x["seconds"], reverse=True)[:12]
    word_midpoints_without_ref=sum(not any(r["start"]<=((w.start+w.end)/2)<r["end"] for r in ref) for w in clip_words)
    return {"source":name,"words":len(clip_words),"segments":len(hyp),"reference_rows":len(ref),
            "reference_unique_covered_s":seconds(ref),"reference_summed_s":ref_duration,
            "untimed_s":DURATION-seconds(ref),"hypothesis_summed_s":sum(h["end"]-h["start"] for h in hyp),
            "word_midpoints_outside_timed_reference":word_midpoints_without_ref,
            "score":scored,"h1_final_der":h1["der"],"mapping":mapping,
            "components_seconds":dict(total),"thirty_second_bins":{k:dict(v) for k,v in bins.items()},
            "near_reference_boundary_seconds":{k:dict(v) for k,v in near.items()},
            "wrong_speaker_pairs_s":dict(sorted(wrong_pairs.items(),key=lambda x:-x[1])),
            "top_error_atoms":top,"top_error_runs":runs,"false_alarm_vad_voiced_frames":fa_voiced,
            "false_alarm_vad_total_frames":fa_frames}


def main():
    c=next(c for c in clips("accept6") if c.clip_id==CASE)
    ref=c.reference_segments();mask=voiced_mask(pcm(CASE))
    canonical=analyze("canonical",words(CASE),ref,mask)
    rows=[canonical]
    root=EVIDENCE/"variance-raw"/CASE
    for draw in range(1,5):
        files=list((root/f"draw-{draw}").glob("*/*.json"))
        if len(files)!=1:raise RuntimeError(f"missing RTFL draw {draw}: {files}")
        raw=json.loads(files[0].read_text())
        rows.append(analyze(f"fresh-{draw}",gc._parse(raw,cached=True).words,ref,mask))
    OUTPUT.write_text(json.dumps({"case_id":CASE,"rows":rows},indent=2)+"\n")
    for r in rows:
        s=r["score"]
        print(r["source"],"DER",s["der"],"miss/FA/confusion",s["miss"],s["false_alarm"],s["speaker_confusion"],
              "timed",r["reference_unique_covered_s"],"overlap",r["components_seconds"]["reference_overlap"],
              "near0.5",{k:round(r["near_reference_boundary_seconds"]["0.5"].get(k,0),2) for k in ("miss","false_alarm","confusion")})
    print("WROTE",OUTPUT)


if __name__=="__main__":main()
