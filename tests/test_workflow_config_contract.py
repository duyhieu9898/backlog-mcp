import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backlog_tool.resolver import (
    category_options,
    find_option,
    issue_type_options,
    status_options,
    resolve_custom_field_defaults,
)
from backlog_tool.settings import load_config, load_project_catalog, load_workflow_config, resolve_user_id
from workflows.ut_bug import merge_bug_defaults
from workflows.resolve_policy import (
    ALWAYS_OVERWRITE_FIELDS,
    GUIDED_FIELDS,
    ONLY_WHEN_EMPTY_FIELDS,
    WORKFLOW_MANAGED_FIELDS,
)


NUMERIC_VALUE_KEYS = {
    "actual_hours",
    "due_in_days",
    "estimated_hours",
}


def assert_no_numeric_ids(test_case, value, path):
    if isinstance(value, dict):
        for key, child in value.items():
            assert_no_numeric_ids(test_case, child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_numeric_ids(test_case, child, f"{path}[{index}]")
        return
    key = path.rsplit(".", 1)[-1]
    if key in NUMERIC_VALUE_KEYS:
        return
    if isinstance(value, int):
        test_case.fail(f"Workflow config must use labels, not raw numeric IDs: {path}")
    if isinstance(value, str) and value.isdigit():
        test_case.fail(f"Workflow config must use labels, not raw numeric IDs: {path}")


class WorkflowConfigContractTest(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_project_catalogs_exist_for_configured_projects(self):
        for project_key in self.config["projects"]:
            catalog = load_project_catalog(project_key)

            self.assertEqual(project_key, catalog["key"])
            self.assertIn("id", catalog)
            self.assertIn("bug", catalog)

    def test_ut_bug_workflow_labels_resolve_for_each_project(self):
        for project_key in self.config["projects"]:
            with self.subTest(project=project_key):
                project = load_project_catalog(project_key)
                defaults = merge_bug_defaults(self.config, project_key)

                self.assertIsNotNone(find_option(issue_type_options(project), defaults["issue_type"], "issue type"))
                self.assertIsNotNone(find_option(status_options(project), defaults["status"], "status"))
                if defaults.get("category"):
                    self.assertIsNotNone(find_option(category_options(project), defaults["category"], "category"))

                payload = resolve_custom_field_defaults(project, defaults.get("custom_fields", {}))
                self.assertTrue(payload)

    def test_resolve_bug_workflow_labels_resolve_for_each_project(self):
        for project_key in self.config["projects"]:
            with self.subTest(project=project_key):
                from workflows.resolve_bug import merge_resolve_defaults
                resolve_workflow = merge_resolve_defaults(self.config, project_key)
                custom_fields = resolve_workflow.get("custom_fields", {})

                project = load_project_catalog(project_key)
                self.assertIsNotNone(find_option(issue_type_options(project), resolve_workflow["issue_type"], "issue type"))
                self.assertIsNotNone(find_option(status_options(project), resolve_workflow["status"], "status"))
                fields = project.get("bug", {}).get("custom_fields", {})

                selections = {
                    "qc_activity": custom_fields["qc_activity"],
                    "bug_origin": custom_fields["bug_origin"],
                    "impacted": custom_fields["impacted"],
                    "corrective_action": "fixed contract test",
                }

                cause_key = "bug_category" if "bug_category" in fields else "cause_category"
                selections[cause_key] = custom_fields[cause_key]

                if "resolution" in fields:
                    selections["resolution"] = custom_fields.get("resolution")

                payload = resolve_custom_field_defaults(project, selections)
                self.assertTrue(payload)

    def test_resolve_policy_field_groups_are_consistent(self):
        self.assertEqual(
            set(WORKFLOW_MANAGED_FIELDS),
            set(ALWAYS_OVERWRITE_FIELDS) | {"resolution"},
        )
        self.assertTrue(set(GUIDED_FIELDS).issubset(ONLY_WHEN_EMPTY_FIELDS))
        self.assertEqual(
            {"qc_activity", "cause_category", "bug_origin", "resolution"},
            set(ONLY_WHEN_EMPTY_FIELDS),
        )

    def test_story_task_overview_workflow_refs_configured_user(self):
        workflow = load_workflow_config("story_task_overview")

        self.assertGreater(len(workflow.get("issue_types", [])), 0)
        self.assertGreater(len(workflow.get("excluded_statuses", [])), 0)
        self.assertIn("issueKey", workflow.get("fields", []))
        self.assertIn("dueAlertLevel", workflow.get("fields", []))
        self.assertIsInstance(resolve_user_id(self.config, workflow["assignee"]), int)

    def test_workflow_configs_use_labels_not_numeric_ids(self):
        for workflow_name in ["ut_bug", "resolve_bug", "story_task_overview"]:
            with self.subTest(workflow=workflow_name):
                assert_no_numeric_ids(self, load_workflow_config(workflow_name), workflow_name)


if __name__ == "__main__":
    unittest.main()
