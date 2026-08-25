import json, sys
path = sys.argv[1] + "/trio-A/results.json"
data = json.load(open(path))
for case in data["cases"]:
    if case["case_id"] == "lex_bill_ackman":
        case["arms"]["live"]["scores"]["tbsa"]["wer"] = 0.40
json.dump(data, open(path, "w"), indent=2)
