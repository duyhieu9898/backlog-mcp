import os

from backlog_tool.telemetry_report import report_from_logs
from backlog_tool.telemetry_rules import apply_rules
from backlog_tool.telemetry_store import group_flows, load_calls

import pytest

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "local", "telemetry-2026-09-23")
pytestmark = pytest.mark.skipif(not os.path.isdir(FIXTURE), reason="local-only fixture built from real logs")


def test_fixture_loads_all_calls():
    calls = load_calls(log_dir=FIXTURE)
    assert len(calls) == 41
    assert sorted({c.client for c in calls}) == ["antigravity-client", "claude-code", "unknown"]


def test_known_findings_from_2026_09_23():
    flows = group_flows(load_calls(log_dir=FIXTURE))
    codes = [f["code"] for flow in flows for f in apply_rules(flow)]
    assert codes.count("generic_after_specialized") == 4
    assert codes.count("duplicate_call") >= 1


def test_report_runs_on_fixture():
    report = report_from_logs(log_dir=FIXTURE)
    assert report["totals"]["calls"] == 41
    assert report["topTools"][0]["tool"] == "resolve_bug"
