import json
import os
import tempfile
from unittest import mock

from backlog_tool import telemetry


def test_begin_tool_trace_writes_vendor_neutral_start_event():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "telemetry.jsonl")
        with mock.patch.object(telemetry.settings, "TELEMETRY_PATH", path), mock.patch.dict(
            os.environ,
            {"BACKLOG_MCP_CLIENT": "codex", "BACKLOG_MCP_CLIENT_VERSION": "test"},
            clear=False,
        ):
            trace_id = telemetry.begin_tool_trace(
                "get_issue",
                {"issue_id": "AQM-1", "view": "compact"},
            )
            telemetry.clear_trace()

        with open(path, "r", encoding="utf-8") as handle:
            record = json.loads(handle.readline())

    assert record["schemaVersion"] == 2
    assert record["event"] == "tool_start"
    assert record["traceId"] == trace_id
    assert record["tool"] == "get_issue"
    assert record["arguments"] == {"issue_id": "AQM-1", "view": "compact"}
    assert record["client"]["name"] == "codex"
    assert record["client"]["version"] == "test"


def test_serialized_bytes_counts_utf8_json_payload():
    value = {"text": "xin chào", "items": [1, 2, 3]}
    measured = telemetry.serialized_bytes(value)
    expected = len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    assert measured == expected


def test_log_write_failure_is_reported_to_stderr_once(capsys, tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setattr(telemetry.settings, "TELEMETRY_PATH", str(blocker / "telemetry.jsonl"))
    monkeypatch.setattr(telemetry.settings, "_reported_log_failures", set())

    telemetry.log_telemetry("tool_start", tool="get_issue")
    telemetry.log_telemetry("tool_start", tool="get_issue")

    err = capsys.readouterr().err
    assert err.count("telemetry.jsonl") == 1
    assert "backlog-mcp: failed to write" in err
