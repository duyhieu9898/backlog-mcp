"""Replay each scenario's expected MCP calls against the real server (stdio) on the fake backend.

No model involved. Proves the server + fake backend can satisfy each scenario and that
the logs grade as PASS. Scenarios that need Plan B (P5) behavior are xfail until then.
"""

import json
import os
import sys

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backlog_tool.telemetry_grader import grade, load_scenarios, render_scenario
from backlog_tool.telemetry_store import group_flows, load_calls
from evals.fake_backlog import FakeBacklog

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NEEDS_PLAN_B = {
    "resolve_fixed": "apply without fix_description is rejected until P5",
    "resolve_multi": "apply without fix_description is rejected until P5",
    "resolve_warning": "apply without fix_description is rejected until P5",
    "fix_context_attachment": "get_bug_context lists attachments in P5",
}


async def _replay(workspace, calls):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "backlog_mcp.server"],
        cwd=str(workspace),
        env={**os.environ, "PYTHONPATH": ROOT, "BACKLOG_WORKSPACE_PATH": str(workspace)},
    )
    results = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for expected in calls:
                results.append(await session.call_tool(expected["tool"], expected["args"]))
    return results


@pytest.mark.parametrize("scenario_id", [s["id"] for s in load_scenarios()])
def test_replay_scenario(scenario_id, tmp_path, request):
    if scenario_id in NEEDS_PLAN_B:
        request.applymarker(pytest.mark.xfail(reason=NEEDS_PLAN_B[scenario_id], strict=True))
    scenario = render_scenario(next(s for s in load_scenarios() if s["id"] == scenario_id))
    log_dir = tmp_path / "eval-logs"
    with FakeBacklog(state=scenario["fakeState"], source="auto") as fake:
        (tmp_path / ".backlog-project.json").write_text(json.dumps({"project_key": "OOP"}))
        (tmp_path / ".backlog-eval.json").write_text(json.dumps({
            "baseUrl": fake.base_url, "logDir": str(log_dir), "runId": "replay-1", "scenario": scenario_id,
        }))
        results = anyio.run(_replay, tmp_path, scenario["expect"]["calls"])
        assert fake.unhandled == []

    assert all(not r.isError for r in results), [r.content[0].text for r in results if r.isError]
    [flow] = group_flows(load_calls(log_dir=str(log_dir)))
    graded = grade(scenario["expect"], flow, final_answer=None)
    assert graded["pass"] is True, graded["reasons"]
    if scenario_id == "fix_context_attachment":
        assert "login-error.png" in json.dumps(results[0].structuredContent)
