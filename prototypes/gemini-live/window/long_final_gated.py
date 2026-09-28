"""PROTOTYPE — zero-send cosine-gated overlap repair of long-final stitch.

Run after long_final.py completes:
  PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
      prototypes/gemini-live/window/long_final_gated.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"common"))
sys.path.insert(0,str(HERE.parent/"continuity"))
import gemini_common as gc  # noqa: E402
from measure import measured_score  # noqa: E402
from registry import cosine  # noqa: E402
from score import score  # noqa: E402
from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder  # noqa: E402
from final_policy import MODEL, cached_words  # noqa: E402
import long_final as l  # noqa: E402

OUTPUT=l.EVIDENCE/"longfinal-gated-overlap.json"


def partition(nodes,excluded,edges):
    groups={n:{n} for n in nodes};member={n:n for n in nodes}
    acoustic=[];overlap=[];vetoed=[];weak=[]
    def compatible(a,b):
        return not any(tuple(sorted((x,y))) in excluded for x in groups[a] for y in groups[b])
    def union(a,b):
        groups[a]|=groups.pop(b)
        for n in groups[a]:member[n]=a
    for a,b,weight in edges:
        ca,cb=nodes[a]["centroid"],nodes[b]["centroid"]
        if ca is not None and cb is not None and cosine(ca,cb)<l.TAU:
            weak.append((a,b,weight,cosine(ca,cb)))
            continue
        ga,gb=member[a],member[b]
        if ga==gb:continue
        if compatible(ga,gb):union(ga,gb);overlap.append((a,b,weight))
        else:vetoed.append((a,b,weight))
    eligible=sorted(n for n in nodes if nodes[n]["centroid"] is not None)
    pairs=[(a,b,cosine(nodes[a]["centroid"],nodes[b]["centroid"]))
           for i,a in enumerate(eligible) for b in eligible[i+1:]]
    for a,b,similarity in sorted(pairs,key=lambda x:(-x[2],x[0],x[1])):
        if similarity<l.TAU:break
        ga,gb=member[a],member[b]
        if ga!=gb and compatible(ga,gb):union(ga,gb);acoustic.append((a,b,similarity))
    return member,{"acoustic_accepted":acoustic,"overlap_accepted":overlap,
                   "overlap_vetoed":vetoed,"overlap_weak":weak}


def main():
    initial=json.loads(l.RESULTS.read_text())
    if len(initial)!=len(l.population()):raise RuntimeError("initial 12 configs incomplete")
    result={}
    embedder=_OnnxWeSpeakerEmbedder(MODEL,device="cpu")
    for c,cap,overlap in l.population():
        key=f"{c.clip_id}|T{cap}|O{overlap}"
        samples=gc.read_wav(c.audio)
        bounds=l.schedule(len(samples)/gc.SAMPLE_RATE,cap,overlap)
        chunks=[]
        for index,b in enumerate(bounds):
            piece=samples[round(b["start"]*gc.SAMPLE_RATE):round(b["end"]*gc.SAMPLE_RATE)]
            chunks.append({"index":index,**b,"words":cached_words(piece).words})
        nodes,all_words,excluded=l.observed(c,chunks,embedder)
        edges,_=l.overlap_edges(chunks,all_words)
        member,edge_info=partition(nodes,excluded,edges)
        words=[gc.Word(w["text"],member[w["node"]],w["start"],w["end"])
               for w in all_words if w["core"]]
        words.sort(key=lambda w:(w.start,w.end))
        hyp=gc.words_to_segments(words)
        scored=(score(c.reference_segments(),hyp,with_text=False) if c.tier=="long30m"
                else measured_score(c.reference_segments(),hyp))
        prior=initial[key]["arms"]["overlap_policy"]
        result[key]={"clip_id":c.clip_id,"tier":c.tier,"cap_s":cap,"overlap_s":overlap,
                     "initial_der":prior["score"]["der"],"candidate_der":scored["der"],
                     "initial_ids":prior["ids"],"candidate_ids":len(set(member.values())),
                     "initial_false_merge_groups":len(prior["diagnostic"]["false_merge_groups"]),
                     "diagnostic":l.identity_diagnostic(c,all_words,member),
                     "edges":edge_info,"mapping":member}
        OUTPUT.write_text(json.dumps(result,indent=2)+"\n")
        r=result[key]
        print("REPLAY",key,"DER",r["initial_der"],"->",r["candidate_der"],
              "IDs",r["initial_ids"],"->",r["candidate_ids"],
              "false",r["initial_false_merge_groups"],"->",len(r["diagnostic"]["false_merge_groups"]),flush=True)
    print("WROTE",OUTPUT,flush=True)


if __name__=="__main__":main()
