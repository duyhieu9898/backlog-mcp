"""Real Backlog API responses extracted from legacy telemetry, re-keyed, for the fake backend.

Cassettes contain real project data and stay local: evals/cassettes/ is git-ignored.
"""

import argparse
import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CASSETTE_PATH = os.path.join(ROOT, "evals", "cassettes", "oop.json")
OPEN_STATUSES = {"Open", "In Progress"}
_KEY = re.compile(r"\b([A-Z][A-Z0-9_]*)-(\d+)\b")


def rekey(key):
    project, number = key.rsplit("-", 1)
    return f"{project}-9{number}"


def _rekey_all(value):
    # Real keys become OOP-9xxxxx so a misconfigured eval can never touch a real issue.
    text = json.dumps(value, ensure_ascii=False)
    return json.loads(_KEY.sub(lambda m: f"{m.group(1)}-9{m.group(2)}", text))


def _rows(path):
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("{"):
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def extract(legacy_path):
    rows = sorted(
        (r for r in _rows(legacy_path)
         if r.get("event") == "api_call" and r.get("tool") and r.get("status") == 200 and r.get("responseBody")),
        key=lambda r: r.get("ts") or "",
    )
    issues, lists, patches, gets_by_trace = {}, [], [], {}
    for row in rows:
        body = json.loads(row["responseBody"])
        path = row["path"]
        if row["method"] == "GET" and path.startswith("/issues/"):
            gets_by_trace.setdefault(row["traceId"], {})[body["issueKey"]] = body
            if (body.get("status") or {}).get("name") in OPEN_STATUSES:
                issues[body["issueKey"]] = body
        elif row["method"] == "GET" and path == "/issues":
            lists.append({
                "ts": row["ts"], "params": (row.get("request") or {}).get("params") or {},
                "result": [item["issueKey"] for item in body], "bodies": body,
            })
        elif row["method"] == "PATCH":
            key = path.split("/")[2]
            before = gets_by_trace.get(row["traceId"], {}).get(key)
            if before is not None:
                patches.append({
                    "ts": row["ts"], "key": key, "before": before,
                    "data": (row.get("request") or {}).get("data") or {}, "after": body,
                })
    return _rekey_all({
        "version": 1, "source": os.path.basename(legacy_path),
        "issues": issues, "lists": lists, "patches": patches,
    })


def load_cassette(path=CASSETTE_PATH):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract a fake-Backlog cassette from legacy telemetry.")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("extract")
    cmd.add_argument("--from", dest="source", required=True)
    cmd.add_argument("--out", default=CASSETTE_PATH)
    args = parser.parse_args(argv)
    cassette = extract(args.source)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(cassette, handle, ensure_ascii=False, indent=1)
    print(f"{args.out}: {len(cassette['issues'])} issues, {len(cassette['lists'])} lists, {len(cassette['patches'])} patches")


if __name__ == "__main__":
    main()
