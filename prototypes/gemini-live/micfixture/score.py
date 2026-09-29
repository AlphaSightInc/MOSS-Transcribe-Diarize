"""Content-based Q-MIC scorer for a completed public HTTP snapshot."""
from __future__ import annotations

import itertools
import json
import re
from array import array
from pathlib import Path

HERE = Path(__file__).resolve().parent


def words(rows, *, entity_key="speaker"):
    out = []
    for row in rows:
        tokens = re.findall(r"[^\W_]+(?:'[^\W_]+)?", row.get("text", "").casefold())
        start, end = float(row["start"]), float(row["end"])
        for i, token in enumerate(tokens):
            out.append({"token": token, "time": start + (i+.5)*(end-start)/len(tokens),
                        "speaker": row.get(entity_key), "index": len(out)})
    return out


def lcs_matches(reference, hypothesis):
    a = [row["token"] for row in reference]
    b = [row["token"] for row in hypothesis]
    table = [array("H", [0]) * (len(b)+1)]
    for token in a:
        prior = table[-1]
        current = array("H", [0]) * (len(b)+1)
        for j, other in enumerate(b, 1):
            current[j] = prior[j-1] + 1 if token == other else max(prior[j], current[j-1])
        table.append(current)
    i, j = len(a), len(b)
    matches = []
    while i and j:
        if a[i-1] == b[j-1] and table[i][j] == table[i-1][j-1]+1:
            matches.append((i-1, j-1))
            i -= 1
            j -= 1
        elif table[i-1][j] >= table[i][j-1]:
            i -= 1
        else:
            j -= 1
    return list(reversed(matches))


def score(snapshot: dict, reference: dict, variant: str,
          *, birth_observations: dict | None = None) -> dict:
    session = snapshot["session"]
    rate = snapshot["descriptor"]["sample_rate"]
    rows = [{"start": row["start_sample"]/rate,
             "end": row["end_sample"]/rate,
             "text": row["text"], "speaker": row.get("canonical_speaker")}
            for row in session["effective_transcript"]
            if row.get("source_lane") == "microphone" and row.get("text", "").strip()]
    hyp = words(rows)
    local_ids = sorted({row["speaker"] for row in hyp
                        if isinstance(row["speaker"], str)
                        and row["speaker"].startswith("local-")})
    refs = {voice: words([row for row in reference["local_turns"]
                          if row["speaker"] == voice]) for voice in ("C", "D")}
    by_id = {identity: [row for row in hyp if row["speaker"] == identity]
             for identity in local_ids}
    best = (0, {}, set())
    for pair in itertools.permutations(local_ids, min(2, len(local_ids))):
        assignment = dict(zip(("C", "D"), pair))
        matches_by_voice = {voice: lcs_matches(refs[voice], by_id.get(assignment.get(voice), []))
                            for voice in ("C", "D")}
        count = sum(len(m) for m in matches_by_voice.values())
        matched_indices = {by_id[assignment[voice]][j]["index"]
                           for voice, matches in matches_by_voice.items()
                           if voice in assignment for _, j in matches}
        if count > best[0]:
            best = (count, {voice: {"local_id": assignment.get(voice),
                                     "retained": len(matches_by_voice[voice]),
                                     "reference_words": len(refs[voice])}
                            for voice in ("C", "D")}, matched_indices)
    if not best[1]:
        best = (0, {voice: {"local_id": None, "retained": 0,
                           "reference_words": len(refs[voice])} for voice in ("C", "D")}, set())
    local_total = sum(len(x) for x in refs.values())
    local_retention = best[0] / local_total if local_total else 0
    echo = None
    if reference["variants"][variant]["echo_db"] is not None:
        system = words(reference["system_turns"])
        remaining = [row for row in hyp if row["index"] not in best[2]]
        used = set()
        leaked = 0
        for row in remaining:
            choices = [(abs(row["time"]-ref["time"]), i)
                       for i, ref in enumerate(system) if i not in used
                       and ref["token"] == row["token"]
                       and abs(row["time"]-ref["time"]) <= 2.0]
            if choices:
                _, i = min(choices)
                used.add(i)
                leaked += 1
        echo = {"reference_system_words": len(system), "leaked_into_mic": leaked,
                "dropped_fraction": 1-leaked/len(system) if system else None,
                "method": "reference tokens with interpolated turn times; local LCS matches removed first"}
    unassigned = set(local_ids) - {v["local_id"] for v in best[1].values()}
    quiet_births = {identity for identity, interval in (birth_observations or {}).items()
                    if not any(turn["start"] < interval["end_s"]
                               and interval["start_s"] < turn["end"]
                               for turn in reference["local_turns"])}
    system_born = sorted(unassigned | quiet_births)
    diagnostics = snapshot.get("engine_diagnostics", {})
    return {"variant": variant, "duration_s": reference["duration_s"],
            "local_ids": local_ids, "local_id_count": len(local_ids),
            "system_born_local_ids": system_born,
            "birth_observations": birth_observations,
            "local_retention": {"retained": best[0], "reference_words": local_total,
                                "fraction": local_retention, "by_voice": best[1]},
            "echo": echo,
            "mic_echo_dropped_by_voice": diagnostics.get("mic_echo_dropped_by_voice"),
            "cost_usd": diagnostics.get("cost_usd"),
            "pass": len(local_ids) == 2 and not system_born and local_retention >= .90
                    and (echo is None or echo["dropped_fraction"] >= .90)}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--variant", required=True)
    args = parser.parse_args()
    reference = json.loads((HERE / "out/reference.json").read_text())
    print(json.dumps(score(json.loads(args.snapshot.read_text()), reference, args.variant), indent=2))


if __name__ == "__main__":
    main()
