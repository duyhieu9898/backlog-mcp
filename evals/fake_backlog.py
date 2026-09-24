"""Local fake of the Backlog API used by the MCP server: replays real recorded issues (cassette)
or a synthetic set with the same keys when no cassette is available."""

import argparse
import copy
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from evals.cassettes import load_cassette

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASE_FIXTURE = os.path.join(ROOT, "tests", "fixtures", "OOP_issue_bug.json")
CATALOG = os.path.join(ROOT, "config", "projects", "OOP.json")
ME = {"id": 778617, "name": "Hieu Nguyen Duy (DN.DEV)"}
REPORTER = {"id": 315996, "name": "QA Reporter"}
# Real "my open bugs" list at 2026-09-23 16:22, re-keyed; plus a bug with a real attachment.
SCENARIO_OPEN = ["OOP-912779", "OOP-912777", "OOP-912774", "OOP-912773", "OOP-912762", "OOP-912749"]
SCENARIO_KEYS = SCENARIO_OPEN + ["OOP-912744"]
RESOLVE_FIELDS = {"QC Activity", "Bug Origin", "Cause Category", "Impacted", "Corrective Action"}


def _catalog():
    with open(CATALOG, encoding="utf-8") as handle:
        bug = json.load(handle)["bug"]
    statuses = {item["id"]: item["name"] for item in bug["status_options"]}
    options = {
        int(cfg["field"].split("_")[1]): cfg.get("value_options") or []
        for cfg in bug["custom_fields"].values()
    }
    return statuses, options


STATUS_NAMES, FIELD_OPTIONS = _catalog()


def display_value(value):
    if isinstance(value, dict):
        return value.get("name")
    if isinstance(value, list):
        return [display_value(item) for item in value]
    return value


def _number(value):
    text = str(value)
    return float(text) if "." in text else int(text)


def apply_patch(issue, data):
    for key, value in data.items():
        value = value[0] if isinstance(value, list) else value
        if key == "statusId":
            status_id = int(value)
            issue["status"] = {**(issue.get("status") or {}), "id": status_id, "name": STATUS_NAMES.get(status_id, "?")}
        elif key == "assigneeId":
            issue["assignee"] = {**(issue.get("assignee") or {}), "id": int(value)}
        elif key in ("startDate", "dueDate"):
            issue[key] = f"{value}T00:00:00Z"
        elif key in ("estimatedHours", "actualHours"):
            issue[key] = _number(value)
        elif key.startswith("customField_"):
            field_id = int(key.split("_")[1])
            options = FIELD_OPTIONS.get(field_id) or []
            chosen = next(({"id": o["id"], "name": o["name"]} for o in options if str(o["id"]) == str(value)), None)
            for field in issue.get("customFields") or []:
                if field["id"] == field_id:
                    field["value"] = chosen if chosen is not None else value
    return issue


def matches_list(issue, params):
    def wanted(name):
        values = params.get(name) or []
        values = values if isinstance(values, list) else [values]
        return {int(v) for v in values}

    checks = (
        ("projectId[]", issue.get("projectId")),
        ("assigneeId[]", (issue.get("assignee") or {}).get("id")),
        ("statusId[]", (issue.get("status") or {}).get("id")),
        ("issueTypeId[]", (issue.get("issueType") or {}).get("id")),
    )
    for name, actual in checks:
        values = wanted(name)
        if values and actual not in values:
            return False
    keyword = params.get("keyword")
    keyword = keyword[0] if isinstance(keyword, list) else keyword
    if keyword:
        text = f"{issue.get('summary') or ''} {issue.get('description') or ''}".lower()
        return keyword.lower() in text
    return True


def _synthetic():
    with open(BASE_FIXTURE, encoding="utf-8") as handle:
        base = json.load(handle)
    issues = {}
    for index, key in enumerate(SCENARIO_KEYS):
        issue = copy.deepcopy(base)
        number = int(key.split("-")[1])
        issue.update({
            "id": number, "keyId": number, "issueKey": key, "summary": f"[Synthetic] Bug {index + 1}",
            "description": "**Actual:** Error 500\n**Expected:** Works",
            "status": {**issue["status"], "id": 1, "name": "Open"},
            "assignee": {**issue["assignee"], **ME}, "createdUser": {**issue["createdUser"], **REPORTER},
            "startDate": None, "dueDate": None, "estimatedHours": None, "actualHours": None, "attachments": [],
        })
        for field in issue["customFields"]:
            if field["name"] in RESOLVE_FIELDS:
                field["value"] = None
            if field["name"] == "Detected Role":
                field["value"] = {"id": 2, "name": "Tester"}
        issues[key] = issue
    issues["OOP-912744"]["attachments"] = [{"id": 7001, "name": "x.png", "size": 48213}]
    return issues


def build_issues(state="default", source="auto"):
    cassette = load_cassette() if source in ("auto", "cassette") else None
    if source == "cassette" and cassette is None:
        raise FileNotFoundError("No cassette. Run: uv run python -m evals.cassettes extract --from logs/legacy/telemetry.jsonl")
    issues = copy.deepcopy(cassette["issues"]) if cassette else _synthetic()
    missing = [key for key in SCENARIO_KEYS if key not in issues]
    if missing:
        raise ValueError(f"Cassette lacks scenario issues: {missing}")
    for key, issue in issues.items():
        if key not in SCENARIO_OPEN or state == "no_open_bugs":
            # A resolved bug is reassigned to its reporter, so it leaves "my open bugs".
            issue["status"] = {**issue["status"], "id": 3, "name": "Resolved"}
            issue["assignee"] = {**(issue.get("assignee") or {}), **{k: issue["createdUser"].get(k) for k in ("id", "name")}}
    # Synthetic tweaks on top of real data (documented in the spec):
    for field in issues["OOP-912749"]["customFields"]:
        if field["name"] == "Detected Role":
            field["value"] = {"id": 1, "name": "Developer"}
    attachment = (issues["OOP-912744"].get("attachments") or [{"id": 7001, "size": 48213}])[0]
    issues["OOP-912744"]["attachments"] = [{**attachment, "name": "login-error.png"}]
    return issues


class _Handler(BaseHTTPRequestHandler):
    fake = None

    def log_message(self, *args):
        return

    def _send(self, status, body):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _route(self, method):
        parsed = urlparse(self.path)
        parts = parsed.path.rstrip("/").split("/")
        query = parse_qs(parsed.query)
        issues = self.fake.issues
        if parts[:4] == ["", "api", "v2", "issues"] and len(parts) == 4 and method == "GET":
            found = [issue for issue in issues.values() if matches_list(issue, query)]
            offset = int((query.get("offset") or [0])[0])
            count = int((query.get("count") or [100])[0])
            return self._send(200, found[offset:offset + count])
        if parts[:4] == ["", "api", "v2", "issues"] and len(parts) == 5:
            issue = issues.get(parts[4])
            if issue is None:
                return self._send(404, {"errors": [{"message": "No issue.", "code": 6}]})
            if method == "GET":
                return self._send(200, issue)
            if method == "PATCH":
                length = int(self.headers.get("Content-Length") or 0)
                form = parse_qs(self.rfile.read(length).decode("utf-8"))
                self.fake.patches.append({"key": parts[4], "form": form})
                return self._send(200, apply_patch(issue, form))
        if parts[:4] == ["", "api", "v2", "projects"] and len(parts) == 5 and method == "GET":
            return self._send(200, {"id": 82531, "projectKey": parts[4], "name": "OOP"})
        self.fake.unhandled.append({"method": method, "path": parsed.path})
        return self._send(404, {"errors": [{"message": f"fake backlog: unhandled {method} {parsed.path}"}]})

    def do_GET(self):
        self._route("GET")

    def do_PATCH(self):
        self._route("PATCH")

    def do_POST(self):
        self._route("POST")


class FakeBacklog:
    def __init__(self, state="default", source="auto", port=0):
        self.issues = build_issues(state, source)
        self.source = "cassette" if source != "synthetic" and load_cassette() is not None else "synthetic"
        self.port = port
        self.patches = []
        self.unhandled = []
        self._server = None
        self.base_url = None

    def start(self):
        handler = type("Handler", (_Handler,), {"fake": self})
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}"
        return self.base_url

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()


def main():
    parser = argparse.ArgumentParser(description="Run the fake Backlog API for manual MCP testing.")
    parser.add_argument("--state", default="default", choices=["default", "no_open_bugs"])
    parser.add_argument("--source", default="auto", choices=["auto", "cassette", "synthetic"])
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    fake = FakeBacklog(args.state, args.source, args.port)
    print(f"Fake Backlog ({fake.source}) at {fake.start()} (Ctrl+C to stop)", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        fake.stop()


if __name__ == "__main__":
    main()
