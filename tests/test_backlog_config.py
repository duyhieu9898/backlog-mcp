import argparse
import unittest
from unittest import mock

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backlog_tool import cli


class BacklogConfigTest(unittest.TestCase):
    def test_config_projects_marks_missing_catalog(self):
        config = {"projects": ["OOP", "AQM"]}

        def fake_load_project_catalog(project_key):
            if project_key == "OOP":
                return {"id": 82531, "name": "Osaka"}
            raise ValueError("missing")

        with mock.patch.object(cli, "load_project_catalog", side_effect=fake_load_project_catalog):
            rows = cli.config_projects(config)

        by_key = {row["key"]: row for row in rows}
        self.assertEqual({"key": "OOP", "id": 82531, "name": "Osaka"}, by_key["OOP"])
        self.assertEqual({"key": "AQM", "id": None, "name": "(missing catalog)"}, by_key["AQM"])


if __name__ == "__main__":
    unittest.main()
