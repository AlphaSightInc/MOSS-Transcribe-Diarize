import json, sys
path = sys.argv[1] + "/keyu5m-B/live/run-001/summary.json"
data = json.load(open(path))
data["accounted_samples"] = int(data["accounted_samples"]) - 16000
json.dump(data, open(path, "w"), indent=2)
