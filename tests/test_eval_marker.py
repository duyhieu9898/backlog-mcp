import json
import os

import pytest

from backlog_tool import settings, telemetry


def write_marker(folder, **overrides):
    marker = {"baseUrl": "http://127.0.0.1:8123", "logDir": str(folder / "logs"), "runId": "r1", "scenario": "open_bugs", **overrides}
    (folder / ".backlog-eval.json").write_text(json.dumps(marker))
    return marker


def test_find_marker_only_in_workspace_root(tmp_path):
    write_marker(tmp_path)
    child = tmp_path / "sub"
    child.mkdir()
    assert settings.find_eval_marker(str(tmp_path))["runId"] == "r1"
    assert settings.find_eval_marker(str(child)) is None
    assert settings.find_eval_marker(None) is None


def test_apply_marker_sets_backend_logs_and_tags(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKLOG_API_KEY", "real-key")
    monkeypatch.delenv("BACKLOG_BASE_URL", raising=False)
    marker = write_marker(tmp_path)
    settings.apply_eval_marker(marker)
    assert os.environ["BACKLOG_BASE_URL"] == "http://127.0.0.1:8123"
    assert os.environ["BACKLOG_API_KEY"] == "eval-fake-key"
    assert settings.LOG_DIR == str(tmp_path / "logs")
    telemetry.start_call("get_my_open_bugs", {})
    telemetry.finish_call("ok", result={}, text="", response_bytes=1)
    row = json.loads(open(telemetry.log_paths()["calls"]).readline())
    assert (row["runId"], row["scenario"]) == ("r1", "open_bugs")


@pytest.mark.parametrize("url", ["https://bapjp.backlog.com", "http://10.0.0.5:80", "http://127.0.0.1.evil.com"])
def test_apply_marker_refuses_non_local_backend(tmp_path, url):
    with pytest.raises(ValueError, match="localhost"):
        settings.apply_eval_marker(write_marker(tmp_path, baseUrl=url))
