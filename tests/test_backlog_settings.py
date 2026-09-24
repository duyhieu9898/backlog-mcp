import os
import tempfile
import unittest
from unittest import mock

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backlog_tool import settings as backlog_settings
from workflows import ut_bug


class BacklogSettingsTest(unittest.TestCase):
    def test_merge_bug_defaults_applies_project_override_and_keeps_custom_fields(self):
        workflow = {
                "issue_type": "Bug",
                "custom_fields": {
                    "qc_activity": "Unit Test",
                    "env": "DEV",
                },
            "project_overrides": {
                "OOP": {
                        "category": "112_DHP",
                        "custom_fields": {
                            "env": "STG",
                            "impacted": "no",
                        },
                },
            },
        }

        with mock.patch.object(ut_bug, "load_workflow_config", return_value=workflow):
            merged = ut_bug.merge_bug_defaults({}, "OOP")

        self.assertEqual("Bug", merged["issue_type"])
        self.assertEqual("112_DHP", merged["category"])
        self.assertEqual(
            {
                "qc_activity": "Unit Test",
                "env": "STG",
                "impacted": "no",
            },
            merged["custom_fields"],
        )

    def test_resolve_project_key_rejects_unknown_project(self):
        config = {
            "base_url": "https://example.backlog.com",
            "projects": ["AQM", "OOP"],
        }

        with self.assertRaisesRegex(ValueError, "Unknown Backlog project"):
            backlog_settings.resolve_project_key(config, "NOPE")

    def test_default_project_key_is_disallowed_in_config(self):
        config = {
            "base_url": "https://example.backlog.com",
            "default_project_key": "AQM",
            "projects": ["AQM", "OOP"],
        }
        with self.assertRaisesRegex(ValueError, "default_project_key is no longer supported"):
            backlog_settings.validate_config(config)

    def test_resolve_project_key_for_issue_prefers_issue_prefix_if_present(self):
        config = {
            "base_url": "https://example.backlog.com",
            "projects": ["AQM", "OOP"],
        }

        self.assertEqual("AQM", backlog_settings.resolve_project_key_for_issue(config, "AQM-123"))

    def test_resolve_project_key_for_issue_rejects_project_mismatch(self):
        config = {
            "base_url": "https://example.backlog.com",
            "projects": ["AQM", "OOP"],
        }

        with self.assertRaisesRegex(ValueError, "does not match --project"):
            backlog_settings.resolve_project_key_for_issue(config, "AQM-123", "OOP")

    def test_resolve_project_key_for_issue_fails_for_numeric_issue_id_without_workspace(self):
        config = {
            "base_url": "https://example.backlog.com",
            "projects": ["AQM", "OOP"],
        }

        with self.assertRaisesRegex(ValueError, "Cannot determine Backlog project"):
            backlog_settings.resolve_project_key_for_issue(config, "12345")

    def test_resolve_project_key_from_local_config(self):
        config = {
            "base_url": "https://example.backlog.com",
            "projects": ["AQM", "OOP", "VTO"],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_config_file = os.path.join(tmp_dir, ".backlog-project.json")
            with open(local_config_file, "w", encoding="utf-8") as f:
                import json
                json.dump({"project_key": "VTO"}, f)
            
            self.assertEqual("VTO", backlog_settings.resolve_project_key(config, start_path=tmp_dir))

    def test_resolve_project_key_stops_at_git_root(self):
        config = {
            "base_url": "https://example.backlog.com",
            "projects": ["AQM", "OOP", "VTO"],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent_dir = os.path.join(tmp_dir, "parent")
            os.makedirs(parent_dir, exist_ok=True)
            with open(os.path.join(parent_dir, ".backlog-project.json"), "w", encoding="utf-8") as f:
                import json
                json.dump({"project_key": "AQM"}, f)
            
            child_dir = os.path.join(parent_dir, "child")
            os.makedirs(os.path.join(child_dir, ".git"), exist_ok=True)
            
            with self.assertRaisesRegex(ValueError, "Cannot determine Backlog project"):
                backlog_settings.resolve_project_key(config, start_path=child_dir)

    def test_resolve_project_key_rejects_malformed_workspace_config(self):
        config = {
            "base_url": "https://example.backlog.com",
            "projects": ["AQM", "OOP"],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_config_file = os.path.join(tmp_dir, ".backlog-project.json")
            with open(local_config_file, "w", encoding="utf-8") as f:
                f.write("{not-json")

            with self.assertRaisesRegex(ValueError, "Invalid workspace config"):
                backlog_settings.resolve_project_key(config, start_path=tmp_dir)

    def test_resolve_project_key_rejects_workspace_config_without_project_key(self):
        config = {
            "base_url": "https://example.backlog.com",
            "projects": ["AQM", "OOP"],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_config_file = os.path.join(tmp_dir, ".backlog-project.json")
            with open(local_config_file, "w", encoding="utf-8") as f:
                f.write("{}")

            with self.assertRaisesRegex(ValueError, "missing project_key"):
                backlog_settings.resolve_project_key(config, start_path=tmp_dir)

    def test_resolve_project_key_invalid_workspace_raises_validation_error(self):
        config = {
            "base_url": "https://example.backlog.com",
            "projects": ["AQM", "OOP"],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_config_file = os.path.join(tmp_dir, ".backlog-project.json")
            with open(local_config_file, "w", encoding="utf-8") as f:
                import json
                json.dump({"project_key": "VTO"}, f)
            
            with self.assertRaisesRegex(ValueError, "Workspace project_key 'VTO' was found, but it is not configured in global backlog.json"):
                backlog_settings.resolve_project_key(config, start_path=tmp_dir)

    def test_resolve_project_key_from_path_convention(self):
        config = {
            "base_url": "https://example.backlog.com",
            "projects": ["AQM", "OOP", "VTO"],
        }
        self.assertEqual("VTO", backlog_settings.resolve_project_key(config, start_path="/home/user/work/VTO/my-app"))
        self.assertEqual("AQM", backlog_settings.resolve_project_key(config, start_path="/home/user/work/aqm/mobile-app"))
        self.assertEqual("OOP", backlog_settings.resolve_project_key(config, start_path="/home/user/work/OOP"))


if __name__ == "__main__":
    unittest.main()
