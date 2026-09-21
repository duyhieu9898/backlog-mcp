import unittest
from unittest import mock

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backlog_tool import inspect as inspect_project


class InspectProjectTest(unittest.TestCase):
    def test_slugify_normalizes_custom_field_names(self):
        self.assertEqual("qc_activity", inspect_project.slugify("QC Activity"))
        self.assertEqual("custom_field", inspect_project.slugify("!!!"))

    def test_build_project_config_collects_reference_metadata(self):
        responses = {
            "/projects/OOP": {"projectKey": "OOP", "name": "Project Name", "id": 82531},
            "/projects/OOP/issueTypes": [{"id": 1, "name": "Bug"}],
            "/projects/OOP/categories": [{"id": 2, "name": "112_DHP"}],
            "/projects/OOP/statuses": [{"id": 3, "name": "Closed"}],
            "/projects/OOP/customFields": [
                {"id": 10, "name": "QC Activity", "items": [{"id": 7, "name": "Unit Test"}]},
                {"id": 11, "name": "QC Activity", "items": []},
            ],
        }

        fake_client = mock.Mock()
        fake_client.request_json.side_effect = lambda method, path: responses[path]

        with mock.patch.object(inspect_project, "BacklogClient", return_value=fake_client):
            result = inspect_project.build_project_config({}, "OOP")

        self.assertEqual("OOP", result["key"])
        self.assertEqual("Project Name", result["name"])
        self.assertEqual(82531, result["id"])
        self.assertEqual([{"id": 1, "name": "Bug"}], result["bug"]["issue_type_options"])
        self.assertEqual([{"id": 2, "name": "112_DHP"}], result["bug"]["category_options"])
        self.assertEqual([{"id": 3, "name": "Closed"}], result["bug"]["status_options"])
        self.assertEqual("customField_10", result["bug"]["custom_fields"]["qc_activity"]["field"])
        self.assertEqual(
            [{"id": 7, "name": "Unit Test"}],
            result["bug"]["custom_fields"]["qc_activity"]["value_options"],
        )
        self.assertEqual("customField_11", result["bug"]["custom_fields"]["qc_activity_11"]["field"])


if __name__ == "__main__":
    unittest.main()
