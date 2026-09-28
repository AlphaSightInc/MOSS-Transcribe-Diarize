"""PROTOTYPE — cap-aware chunk stitch, public Lex30m and synthetic s1 clips.

One command: PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
  prototypes/gemini-live/window/long_final.py
Use --plan for a zero-send schedule preview. Receipts make reruns cache-only.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
sys.path.insert(0, str(HERE.parent / "continuity"))
import gemini_common as gc  # noqa: E402
from corpus import clips  # noqa: E402
from measure import embedding_intervals, measured_score  # noqa: E402
from registry import cosine  # noqa: E402
from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder  # noqa: E402
from score import score  # noqa: E402
from final_policy import MODEL, VECTORS, case_result, turns_and_exclusions, unit  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P53")
CALLS = EVIDENCE / "longfinal-calls.json"
RESULTS = EVIDENCE / "longfinal-results.json"
STATUS = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/status/PANE-5.3-STATUS.md")
LANE = "P53-longfinal"
CAP = 3.0
TAU = .65
GAP = 2.0


def note(message):
    row = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} LONGFINAL {message}"
    with STATUS.open("a") as out:
        out.write(row + "\n")
    print(row, flush=True)


def population():
    all_clips = clips()
    lex = next(c for c in all_clips if c.clip_id == "benchmark_30m:lex_bill_ackman")
    synth = [c for c in all_clips if c.tier == "synth" and c.clip_id.endswith("_s1")]
    return [(lex, cap, overlap) for cap in (900, 600) for overlap in (30, 60)] + [
        (c, 300, overlap) for c in synth for overlap in (30, 60)]


def schedule(duration, cap, overlap):
    assert 0 < overlap < cap and duration > cap
    out = []
    start = 0.0
    while start < duration:
        end = min(duration, start + cap)
        core_end = duration if end == duration else start + cap - overlap
        out.append({"start": start, "end": end, "core_start": start, "core_end": core_end})
        start = core_end
    assert all(x["end"]-x["start"] <= cap+1e-6 for x in out)
    assert all(abs(out[i]["end"]-out[i+1]["start"]-overlap)<1e-6 for i in range(len(out)-1))
    assert out[0]["core_start"] == 0 and out[-1]["core_end"] == duration
    return out


def call_chunks(c, cap, overlap, calls):
    samples = gc.read_wav(c.audio)
    duration = len(samples)/gc.SAMPLE_RATE
    plan = schedule(duration, cap, overlap)
    chunks = []
    for index, bounds in enumerate(plan):
        key = f"{c.clip_id}|T{cap}|O{overlap}|c{index}"
        lo, hi = round(bounds["start"]*gc.SAMPLE_RATE),round(bounds["end"]*gc.SAMPLE_RATE)
        part = samples[lo:hi]
        spent = sum(x["cost_usd"] for x in calls.values())
        if key not in calls and spent + len(part)/gc.SAMPLE_RATE*.0002 >= CAP:
            raise RuntimeError(f"$3 guard before {key}: ${spent:.4f} spent")
        result = gc.diarize_window(part, use_cache=True, max_attempts=3, ledger_lane=LANE)
        if key not in calls:
            calls[key] = {"clip_id": c.clip_id, "cap_s": cap, "overlap_s": overlap,
                          "chunk": index, **bounds, "audio_s": len(part)/gc.SAMPLE_RATE,
                          "cached": result.cached, "latency_s": result.latency_s,
                          "cost_usd": 0 if result.cached else result.cost_usd(),
                          "words": len(result.words), "labels": len({w.speaker for w in result.words}),
                          "timing_anomalies": result.timing_anomalies}
            CALLS.write_text(json.dumps(calls,indent=2)+"\n")
            note(f"CALL {key} {len(part)/gc.SAMPLE_RATE:.0f}s words={len(result.words)} "
                 f"labels={calls[key]['labels']} anomaly={result.timing_anomalies} "
                 f"cached={result.cached} cost=${calls[key]['cost_usd']:.4f} "
                 f"spent=${sum(x['cost_usd'] for x in calls.values()):.4f}")
        chunks.append({"index": index, **bounds, "words": result.words})
    return chunks


def observed(c, chunks, embedder):
    nodes = {}
    all_words = []
    excluded = set()
    for chunk in chunks:
        i, start = chunk["index"], chunk["start"]
        local = [w.__dict__ for w in chunk["words"]]
        _, motifs = turns_and_exclusions(chunk["words"], GAP)
        excluded.update(tuple(sorted((f"c{i}:{a}",f"c{i}:{b}"))) for a,b in motifs)
        for label in sorted({w.speaker for w in chunk["words"]}):
            node = f"c{i}:{label}"
            intervals = embedding_intervals(start, local, label)
            vectors = embedder.embed_intervals(c.audio, intervals) if intervals else []
            nodes[node] = {"chunk":i,"local_label":label,"intervals":intervals,
                           "vectors":vectors,"centroid":unit(vectors) if vectors else None}
        for w in chunk["words"]:
            all_words.append({"node":f"c{i}:{w.speaker}","chunk":i,"start":start+w.start,
                              "end":start+w.end,"text":w.text,
                              "core":chunk["core_start"] <= start+(w.start+w.end)/2 < chunk["core_end"]})
    return nodes, all_words, excluded


def overlap_edges(chunks, all_words):
    edges = []
    seams = []
    for i in range(1,len(chunks)):
        prior, current = chunks[i-1],chunks[i]
        lo,hi=current["start"],prior["end"]
        left=[x for x in all_words if x["chunk"]==i-1 and x["end"]>lo and x["start"]<hi]
        right=[x for x in all_words if x["chunk"]==i and x["end"]>lo and x["start"]<hi]
        weights=defaultdict(float)
        for p in left:
            for q in right:
                weights[(p["node"],q["node"])]+=max(0.0,min(p["end"],q["end"])-max(p["start"],q["start"]))
        used_left=set();used_right=set();matched=[]
        for (a,b),weight in sorted(weights.items(),key=lambda x:(-x[1],x[0])):
            if weight<=0 or a in used_left or b in used_right:continue
            used_left.add(a);used_right.add(b)
            edges.append((a,b,weight))
            matched.append({"prior":a,"current":b,"cooccurrence_s":weight})
        seams.append({"chunk":i,"start":lo,"end":hi,"prior_labels":sorted({x["node"] for x in left}),
                      "current_labels":sorted({x["node"] for x in right}),"matched":matched})
    return edges,seams


def partitions(nodes, excluded, edges, use_policy):
    groups={n:{n} for n in nodes}
    member={n:n for n in nodes}
    accepted_overlap=[];rejected_overlap=[];accepted_acoustic=[];rejected_acoustic=[]
    def compatible(a,b):
        return not any(tuple(sorted((x,y))) in excluded for x in groups[a] for y in groups[b])
    def combine(a,b):
        groups[a]|=groups.pop(b)
        for n in groups[a]:member[n]=a
    for a,b,weight in edges:
        ga,gb=member[a],member[b]
        if ga==gb:continue
        if use_policy and not compatible(ga,gb):
            rejected_overlap.append((a,b,weight))
        else:
            combine(ga,gb);accepted_overlap.append((a,b,weight))
    if use_policy:
        eligible=sorted(n for n in nodes if nodes[n]["centroid"] is not None)
        candidates=[(a,b,cosine(nodes[a]["centroid"],nodes[b]["centroid"]))
                    for i,a in enumerate(eligible) for b in eligible[i+1:]]
        for a,b,similarity in sorted(candidates,key=lambda x:(-x[2],x[0],x[1])):
            if similarity<TAU:break
            ga,gb=member[a],member[b]
            if ga==gb:continue
            if compatible(ga,gb):
                combine(ga,gb);accepted_acoustic.append((a,b,similarity))
            else:rejected_acoustic.append((a,b,similarity))
    return member,{"overlap_accepted":accepted_overlap,"overlap_vetoed":rejected_overlap,
                   "acoustic_accepted":accepted_acoustic,"acoustic_vetoed":rejected_acoustic}


def identity_diagnostic(c, all_words, member):
    support=defaultdict(lambda:defaultdict(float))
    reference=c.reference_segments()
    for w in all_words:
        if not w["core"]:continue
        for r in reference:
            amount=max(0.0,min(w["end"],r["end"])-max(w["start"],r["start"]))
            if amount:support[w["node"]][r["speaker"]]+=amount
    dominant={}
    for node,votes in support.items():
        speaker,amount=max(votes.items(),key=lambda x:x[1])
        if amount>=.5 and amount/sum(votes.values())>=.70:dominant[node]=speaker
    groups=defaultdict(set)
    for node,meeting_id in member.items():groups[meeting_id].add(node)
    false=[{"members":sorted(nodes),"truth":sorted({dominant[n] for n in nodes if n in dominant})}
           for nodes in groups.values() if len({dominant[n] for n in nodes if n in dominant})>1]
    splits=defaultdict(set)
    for node,speaker in dominant.items():splits[speaker].add(member[node])
    return {"false_merge_groups":false,"residual_splits":sum(max(0,len(v)-1) for v in splits.values()),
            "attributed_nodes":len(dominant),"unattributed_nodes":len(member)-len(dominant)}


def evaluate(c, chunks, embedder):
    nodes,all_words,excluded=observed(c,chunks,embedder)
    edges,seams=overlap_edges(chunks,all_words)
    vectors=json.loads(VECTORS.read_text())
    whole=case_result(c,vectors[c.clip_id],TAU,GAP,True,"single")
    whole_pure=case_result(c,vectors[c.clip_id],2.0,0.0,False,"single")
    arms={}
    for name,use_policy in (("overlap",False),("overlap_policy",True)):
        member,edge_info=partitions(nodes,excluded,edges,use_policy)
        core=[gc.Word(x["text"],member[x["node"]],x["start"],x["end"])
              for x in all_words if x["core"]]
        core.sort(key=lambda w:(w.start,w.end))
        hyp=gc.words_to_segments(core)
        metric=(score(c.reference_segments(),hyp,with_text=False) if c.tier=="long30m"
                else measured_score(c.reference_segments(),hyp))
        arms[name]={"score":metric,"ids":len(set(member.values())),"core_words":len(core),
                    "diagnostic":identity_diagnostic(c,all_words,member),
                    "seam_matches":len(edge_info["overlap_accepted"]),
                    "seam_vetoes":len(edge_info["overlap_vetoed"]),
                    "acoustic_merges":len(edge_info["acoustic_accepted"]),
                    "acoustic_vetoes":len(edge_info["acoustic_vetoed"]),
                    "mapping":member,"edge_info":edge_info}
    return {"clip_id":c.clip_id,"tier":c.tier,"duration_s":len(gc.read_wav(c.audio))/gc.SAMPLE_RATE,
            "chunks":len(chunks),"nodes":len(nodes),"eligible_nodes":sum(v["centroid"] is not None for v in nodes.values()),
            "seams":seams,"excluded_pairs":len(excluded),"whole_pure_der":whole_pure["der"],
            "whole_policy_der":whole["der"],"whole_pure_ids":whole_pure["output_labels"],
            "whole_policy_ids":whole["output_labels"],"truth_ids":whole["truth_speakers"],"arms":arms}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",action="store_true")
    args=parser.parse_args()
    plans=population()
    total_s=0
    for c,cap,overlap in plans:
        duration=len(gc.read_wav(c.audio))/gc.SAMPLE_RATE
        chunks=schedule(duration,cap,overlap)
        total_s+=sum(x["end"]-x["start"] for x in chunks)
        print("PLAN",c.clip_id,"cap",cap,"overlap",overlap,"chunks",len(chunks),
              "calls",[(x["start"],x["end"],x["core_end"]) for x in chunks],flush=True)
    print("PLAN TOTAL",len(plans),"configs",sum(len(schedule(len(gc.read_wav(c.audio))/gc.SAMPLE_RATE,cap,o))
                                          for c,cap,o in plans),"call slots",total_s,"audio seconds",flush=True)
    if args.plan:return
    calls=json.loads(CALLS.read_text()) if CALLS.exists() else {}
    note(f"START {len(plans)} configs, {len(calls)} prior call receipts, cap=${CAP:.2f}")
    embedder=_OnnxWeSpeakerEmbedder(MODEL,device="cpu")
    results=json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    for c,cap,overlap in plans:
        key=f"{c.clip_id}|T{cap}|O{overlap}"
        if key in results:continue
        chunks=call_chunks(c,cap,overlap,calls)
        row=evaluate(c,chunks,embedder)
        row.update({"cap_s":cap,"overlap_s":overlap})
        results[key]=row
        RESULTS.write_text(json.dumps(results,indent=2,default=str)+"\n")
        a,b=row["arms"]["overlap"],row["arms"]["overlap_policy"]
        note(f"RESULT {key}: DER {a['score']['der']:.6f}/{b['score']['der']:.6f} "
             f"IDs {a['ids']}/{b['ids']} one-call {row['whole_pure_der']:.6f}/{row['whole_policy_der']:.6f} "
             f"false-merge {len(a['diagnostic']['false_merge_groups'])}/{len(b['diagnostic']['false_merge_groups'])} "
             f"spent=${sum(x['cost_usd'] for x in calls.values()):.4f}")
    note(f"COMPLETE {len(results)}/{len(plans)} configs, {len(calls)} call slots, "
         f"spent=${sum(x['cost_usd'] for x in calls.values()):.4f}")
    for key,row in results.items():
        a,b=row["arms"]["overlap"],row["arms"]["overlap_policy"]
        print("ROW",key,"DER",a["score"]["der"],b["score"]["der"],
              "IDs",a["ids"],b["ids"],"false",len(a["diagnostic"]["false_merge_groups"]),
              len(b["diagnostic"]["false_merge_groups"]),flush=True)


if __name__=="__main__":main()
