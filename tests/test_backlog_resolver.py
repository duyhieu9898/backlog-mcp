import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backlog_tool import resolver as backlog_resolver


PROJECT = {
    "bug": {
        "issue_type_options": [
            {"id": 1, "name": "Bug"},
        ],
        "category_options": [
            {"id": 2, "name": "112_DHP"},
        ],
        "status_options": [
            {"id": 3, "name": "Closed"},
        ],
        "custom_fields": {
            "qc_activity": {
                "field": "customField_10",
                "label": "QC Activity",
                "value_options": [
                    {"id": 7, "name": "Unit Test"},
                ],
            },
            "note": {
                "field": "customField_11",
                "label": "Note",
            },
        },
    },
}


class BacklogResolverTest(unittest.TestCase):
    def test_find_option_accepts_numeric_id_string(self):
        self.assertEqual(7, backlog_resolver.find_option([], "7", "field"))

    def test_resolve_issue_type_and_category_use_catalog_labels(self):
        self.assertEqual(1, backlog_resolver.resolve_issue_type(PROJECT, "Bug"))
        self.assertEqual(2, backlog_resolver.resolve_category(PROJECT, "112_DHP"))
        self.assertEqual(3, backlog_resolver.resolve_status(PROJECT, "Closed"))

    def test_resolve_custom_fields_supports_option_and_plain_values(self):
        payload = backlog_resolver.resolve_custom_fields(
            PROJECT,
            ["qc_activity=Unit Test", "note=free text"],
        )

        self.assertEqual(
            {
                "customField_10": 7,
                "customField_11": "free text",
            },
            payload,
        )

    def test_resolve_custom_field_defaults_fails_for_unknown_default(self):
        with self.assertRaisesRegex(ValueError, "Unknown custom field"):
            backlog_resolver.resolve_custom_field_defaults(PROJECT, {"missing": "value"})


if __name__ == "__main__":
    unittest.main()
