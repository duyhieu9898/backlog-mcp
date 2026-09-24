import argparse
import unittest

import json as _json
import os as _os
import sys
from pathlib import Path
from unittest import mock as _mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backlog_tool import cli, presenter
from backlog_tool import telemetry


RAW_ISSUE = {
    "issueKey": "AQM-1",
    "summary": "Something",
    "issueType": {"name": "Bug"},
    "status": {"name": "Open"},
    "assignee": {"id": 1, "name": "Me", "nulabAccount": {"iconUrl": "x"}},
    "priority": {"name": "Normal"},
    "customFields": [
        {"id": 1, "name": "QC Activity", "value": {"id": 5, "name": "Integration Test"}},
        {"id": 2, "name": "Detected Role", "value": [{"id": 2, "name": "Tester"}]},
    ],
}


class ParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = cli.build_parser()

    def test_write_actions_default_to_dry_run(self):
        for argv in (
            ["issue", "create", "S", "--issue-type", "Bug"],
            ["issue", "update", "AQM-1", "--comment", "c"],
            ["bug", "resolve", "AQM-1"],
            ["bug", "create-ut", "AQM-1", "FE", "desc"],
        ):
            args = self.parser.parse_args(argv)
            self.assertTrue(cli.is_dry_run(args), argv)
            self.assertFalse(args.apply, argv)

    def test_apply_flag_disables_dry_run(self):
        args = self.parser.parse_args(["bug", "resolve", "AQM-1", "--apply"])
        self.assertFalse(cli.is_dry_run(args))

    def test_read_actions_have_no_dry_run(self):
        args = self.parser.parse_args(["issue", "get", "AQM-1"])
        self.assertIsNone(cli.is_dry_run(args))

    def test_telemetry_commands_parse(self):
        args = self.parser.parse_args(["telemetry", "report", "--since", "1d", "--run", "r1"])
        self.assertEqual(("telemetry", "report", "1d", "r1"), (args.group, args.action, args.since, args.run))
        args = self.parser.parse_args(["telemetry", "import-claude"])
        self.assertEqual(("telemetry", "import-claude"), (args.group, args.action))
        self.assertIsNone(cli.is_dry_run(args))

    def test_command_name(self):
        args = self.parser.parse_args(["bug", "resolve", "AQM-1"])
        self.assertEqual("bug:resolve", cli.command_name(args))

    def test_config_audit_workflows_is_available(self):
        args = self.parser.parse_args(["config", "audit-workflows"])
        self.assertEqual("audit-workflows", args.action)

    def test_resolve_accepts_commit_ref(self):
        args = self.parser.parse_args(["bug", "resolve", "AQM-1", "--commit", "30e0ca6"])
        self.assertEqual("30e0ca6", args.commit)


class PresenterRoutingTest(unittest.TestCase):
    def setUp(self):
        self.parser = cli.build_parser()

    def test_compact_issue_drops_verbose_user_fields(self):
        result = presenter.compact_issue(RAW_ISSUE)
        self.assertEqual("Me", result["assignee"])
        self.assertEqual("Integration Test", result["customFields"][0]["value"])
        self.assertEqual(["Tester"], result["customFields"][1]["value"])
        self.assertNotIn("nulabAccount", result)

    def test_present_get_is_compact_by_default(self):
        args = self.parser.parse_args(["issue", "get", "AQM-1"])
        out = cli.present(RAW_ISSUE, args)
        self.assertEqual("AQM-1", out["issueKey"])
        self.assertNotIn("nulabAccount", out.get("assignee", ""))

    def test_present_json_full_passes_through(self):
        args = self.parser.parse_args(["--json-full", "issue", "get", "AQM-1"])
        out = cli.present(RAW_ISSUE, args)
        self.assertIs(out, RAW_ISSUE)

    def test_json_full_works_after_action(self):
        # main() strips --json-full from argv before parsing, so it works in any
        # position (root or after the action). Simulate that preprocessing.
        argv = ["issue", "get", "AQM-1", "--json-full"]
        json_full = "--json-full" in argv
        argv = [t for t in argv if t != "--json-full"]
        args = self.parser.parse_args(argv)
        if json_full:
            args.json_full = True
        self.assertTrue(args.json_full)
        self.assertIs(cli.present(RAW_ISSUE, args), RAW_ISSUE)

    def test_present_resolve_dry_run_keeps_changes_and_warnings(self):
        args = self.parser.parse_args(["bug", "resolve", "AQM-1"])
        built = {"dryRun": True, "issue": "AQM-1", "project": "AQM",
                 "assignment": {"to": {"name": "Reporter"}, "source": "createdUser (reporter)"},
                 "changes": [{"field": "Status"}], "warnings": ["w"], "context": {"big": "x"}}
        out = cli.present(built, args)
        self.assertEqual("Reporter", out["assignment"]["to"]["name"])
        self.assertEqual([{"field": "Status"}], out["changes"])
        self.assertEqual(["w"], out["warnings"])
        self.assertNotIn("context", out)

    def test_present_bug_context_keeps_reporter(self):
        args = self.parser.parse_args(["bug", "context", "AQM-1"])
        context = {
            "issueKey": "AQM-1",
            "assignee": {"id": 1, "name": "Developer"},
            "createdUser": {"id": 2, "name": "Reporter"},
        }

        out = cli.present(context, args)

        self.assertEqual("Reporter", out["createdUser"]["name"])

    def test_present_story_overview_keeps_due_alert_fields(self):
        args = self.parser.parse_args(["story", "overview"])
        result = [
            {
                "issueKey": "AQM-1",
                "status": "Open",
                "daysUntilDue": 0,
                "dueAlertLevel": 2,
            }
        ]

        self.assertEqual(result, cli.present(result, args))


class CliTelemetryTest(unittest.TestCase):
    def _rows(self, kind):
        with open(telemetry.log_paths()[kind], encoding="utf-8") as handle:
            return [_json.loads(line) for line in handle if line.strip()]

    def test_cli_command_traced_under_mcp_tool_name(self):
        with _mock.patch.object(cli, "load_config", return_value={"base_url": "https://x"}), \
             _mock.patch.object(cli, "run_handler", return_value={"dryRun": True, "issue": "OOP-1"}), \
             _mock.patch.object(cli, "resolve_project_key_for_issue", return_value="OOP"):
            cli.execute(["bug", "resolve", "OOP-1"])
        [call] = self._rows("calls")
        [session] = self._rows("sessions")
        self.assertEqual(("resolve_bug", "cli", "ok", "preview"), (call["tool"], call["surface"], call["status"], call["mode"]))
        self.assertEqual("cli", session["surface"])
        folder = telemetry.log_paths()["details_dir"]
        detail = _json.loads(open(_os.path.join(folder, _os.listdir(folder)[0]), encoding="utf-8").readline())
        self.assertEqual("OOP-1", detail["arguments"]["issue_key"])

    def test_cli_error_closes_trace(self):
        with _mock.patch.object(cli, "load_config", side_effect=ValueError("bad config")):
            with self.assertRaises(ValueError):
                cli.execute(["bug", "context", "OOP-1"])
        [call] = self._rows("calls")
        self.assertEqual(("get_bug_context", "error"), (call["tool"], call["status"]))
        self.assertEqual("bad config", self._rows("errors")[0]["message"])
        self.assertIsNone(telemetry.current_trace_id())

    def test_telemetry_command_does_not_store_report_in_details(self):
        report = {"flows": [{"prompt": "secret prompt text"}], "totals": {}}
        with _mock.patch.object(cli, "load_config", return_value={"base_url": "https://x"}), \
             _mock.patch.object(cli, "run_handler", return_value=report):
            result = cli.execute(["telemetry", "report", "--json"])
        self.assertIn("secret prompt text", result.text)
        [call] = self._rows("calls")
        self.assertEqual("ok", call["status"])
        self.assertGreater(call["responseBytes"], 0)
        folder = telemetry.log_paths()["details_dir"]
        detail = _json.loads(open(_os.path.join(folder, _os.listdir(folder)[0]), encoding="utf-8").readline())
        self.assertNotIn("result", detail)
        self.assertNotIn("text", detail)


if __name__ == "__main__":
    unittest.main()
