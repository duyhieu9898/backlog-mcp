import os

import pytest

from backlog_tool import settings


@pytest.fixture(autouse=True)
def isolated_log_paths(request, tmp_path, monkeypatch):
    """Keep test runs out of the real logs/ (calls/errors/sessions/details).

    Tool handlers log every call, so without this fixture each pytest run
    appended fake records (sub-millisecond durations, "Boom" errors) to the
    workstation's logs/ and skewed workflow analysis.
    """
    if request.node.get_closest_marker("real_log_paths"):
        yield
        return
    from backlog_tool import telemetry

    monkeypatch.setattr(settings, "LOG_DIR", str(tmp_path / "logs"))
    telemetry.set_eval_tags(None, None)
    telemetry.set_surface("mcp")
    yield
    telemetry.set_eval_tags(None, None)
