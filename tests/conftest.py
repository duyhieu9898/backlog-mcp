import os

import pytest

from backlog_tool import settings

try:  # removed in Task 5
    from backlog_tool import journal
except ImportError:
    journal = None


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
    from backlog_tool import telemetry

    monkeypatch.setattr(settings, "LOG_DIR", str(tmp_path / "logs"))
    # Transitional until Task 5 removes the legacy sinks: keep them out of the real logs/.
    for name, filename in (("LOG_PATH", "backlog.log"), ("METRICS_PATH", "metrics.log"), ("TELEMETRY_PATH", "telemetry.jsonl")):
        if hasattr(settings, name):
            monkeypatch.setattr(settings, name, str(tmp_path / "logs" / filename))
    if journal is not None:
        monkeypatch.setattr(journal, "SESSIONS_DIR", str(tmp_path / "logs" / "sessions"))
    telemetry.set_eval_tags(None, None)
    telemetry.set_surface("mcp")
    yield
    telemetry.set_eval_tags(None, None)
