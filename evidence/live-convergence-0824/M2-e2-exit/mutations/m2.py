import json, sys
# Both passes: the gate scores the MEAN of the two, so a single mutated pass is still an
# improvement on average and would prove nothing.
for run in ("A", "B"):
    path = f"{sys.argv[1]}/trio-{run}/results.json"
    data = json.load(open(path))
    for case in data["cases"]:
        if case["case_id"] == "lex_javier_milei":
            # exactly the baseline: an unchanged case must not read as an improvement
            case["arms"]["live"]["scores"]["tbsa"]["wer"] = 0.144
    json.dump(data, open(path, "w"), indent=2)
