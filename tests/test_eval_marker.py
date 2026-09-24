import json
import os

import pytest

from backlog_tool import settings, telemetry
from backlog_mcp import server


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


@pytest.mark.parametrize("url", ["https://bapjp.backlog.com", "http://10.0.0.5:80", "http://127.0.0.1.evil.com", "https://127.0.0.1:8123"])
def test_apply_marker_refuses_non_local_backend(tmp_path, url):
    with pytest.raises(ValueError, match="localhost"):
        settings.apply_eval_marker(write_marker(tmp_path, baseUrl=url))


def test_activate_workspace_reloads_config(tmp_path, monkeypatch):
    """activate_workspace finds marker, applies it, and reloads config singleton."""
    monkeypatch.delenv("BACKLOG_BASE_URL", raising=False)
    monkeypatch.delenv("BACKLOG_API_KEY", raising=False)
    # Save original singleton state
    original_config = server._config
    original_error = server._bootstrap_error

    try:
        # Reset singleton so it bootstraps fresh
        server._config = None
        server._bootstrap_error = None

        # Create marker and activate
        write_marker(tmp_path)
        marker = server.activate_workspace(str(tmp_path))

        assert marker is not None
        assert marker["runId"] == "r1"

        # Config should be reloaded with fake backend URL
        config = server.get_config_instance()
        assert config["base_url"] == "http://127.0.0.1:8123"
        assert settings.api_base_url(config) == "http://127.0.0.1:8123/api/v2"
        assert settings.require_api_key() == "eval-fake-key"
    finally:
        # Restore original singleton state
        server._config = original_config
        server._bootstrap_error = original_error


def test_activate_workspace_no_marker_unchanged(tmp_path, monkeypatch):
    """activate_workspace returns None if no marker, and config singleton unchanged."""
    # Save original singleton
    original_config = server._config
    original_error = server._bootstrap_error

    try:
        # activate_workspace on empty directory should return None
        marker = server.activate_workspace(str(tmp_path))
        assert marker is None

        # Config singleton should be unchanged (same object identity)
        assert server._config is original_config
        assert server._bootstrap_error is original_error
    finally:
        # Restore original singleton state
        server._config = original_config
        server._bootstrap_error = original_error


def test_activate_workspace_bad_url_unchanged(tmp_path, monkeypatch):
    """activate_workspace with bad URL raises ValueError and config unchanged."""
    monkeypatch.delenv("BACKLOG_BASE_URL", raising=False)
    # Save original singleton
    original_config = server._config
    original_error = server._bootstrap_error

    try:
        write_marker(tmp_path, baseUrl="https://bapjp.backlog.com")

        with pytest.raises(ValueError, match="localhost"):
            server.activate_workspace(str(tmp_path))

        # Config should be unchanged if it exists
        if original_config is not None:
            assert server.get_config_instance() is original_config
    finally:
        # Restore original singleton state
        server._config = original_config
        server._bootstrap_error = original_error
