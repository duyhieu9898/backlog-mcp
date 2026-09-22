import os

import pytest

from backlog_tool import journal, settings


@pytest.fixture(autouse=True)
def isolated_log_paths(request, tmp_path, monkeypatch):
    """Keep test runs out of the real logs/ metrics, telemetry, and CLI journal.

    Tool handlers log every call, so without this fixture each pytest run
    appended fake records (sub-millisecond durations, "Boom" errors) to the
    workstation's metrics.log/telemetry.jsonl and skewed workflow analysis.
    """
    if request.node.get_closest_marker("real_log_paths"):
        yield
        return
    log_dir = str(tmp_path / "logs")
    monkeypatch.setattr(settings, "LOG_DIR", log_dir)
    monkeypatch.setattr(settings, "LOG_PATH", os.path.join(log_dir, "backlog.log"))
    monkeypatch.setattr(settings, "METRICS_PATH", os.path.join(log_dir, "metrics.log"))
    monkeypatch.setattr(settings, "TELEMETRY_PATH", os.path.join(log_dir, "telemetry.jsonl"))
    monkeypatch.setattr(journal, "SESSIONS_DIR", os.path.join(log_dir, "sessions"))
    yield
