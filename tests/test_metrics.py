import json
import os
import tempfile
import unittest
from unittest import mock

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backlog_tool import settings


class MetricsTest(unittest.TestCase):
    def test_log_metric_and_summarize(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics_path = os.path.join(tmp, "metrics.log")
            with mock.patch.object(settings, "METRICS_PATH", metrics_path), mock.patch.object(
                settings, "LOG_DIR", tmp
            ):
                settings.log_metric("issue:get", 1000, 50, "ok", dry_run=None, project="AQM")
                settings.log_metric("issue:get", 2000, 150, "ok", dry_run=None, project="AQM")
                settings.log_metric("bug:resolve", 100, 10, "error", dry_run=True, project="AQM")

                summary = settings.summarize_metrics()

        self.assertEqual(3, summary["totalRuns"])
        by_command = {row["command"]: row for row in summary["commands"]}
        self.assertEqual(2, by_command["issue:get"]["runs"])
        self.assertEqual(1500, by_command["issue:get"]["avgOutputBytes"])
        self.assertEqual(1, by_command["bug:resolve"]["errors"])
        # ordered by totalOutputBytes desc
        self.assertEqual("issue:get", summary["commands"][0]["command"])

    def test_read_metrics_skips_bad_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics_path = os.path.join(tmp, "metrics.log")
            with open(metrics_path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"command": "x", "outputBytes": 10}) + "\n")
                handle.write("not json\n")
            with mock.patch.object(settings, "METRICS_PATH", metrics_path):
                records = settings.read_metrics()
        self.assertEqual(1, len(records))


if __name__ == "__main__":
    unittest.main()
