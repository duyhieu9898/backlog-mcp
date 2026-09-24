import copy

import pytest

from evals.cassettes import load_cassette
from evals.fake_backlog import SCENARIO_KEYS, apply_patch, display_value, matches_list

CASSETTE = load_cassette()
pytestmark = pytest.mark.skipif(CASSETTE is None, reason="no local cassette (evals/cassettes/ is git-ignored)")


def test_cassette_has_every_scenario_issue():
    assert set(SCENARIO_KEYS) <= set(CASSETTE["issues"])


def test_every_recorded_list_result_passes_the_fake_filter():
    for record in CASSETTE["lists"]:
        for body in record["bodies"]:
            assert matches_list(body, record["params"]), (record["ts"], body["issueKey"])


def test_every_recorded_patch_is_reproduced():
    assert CASSETTE["patches"], "cassette has no PATCH pairs"
    for record in CASSETTE["patches"]:
        got = apply_patch(copy.deepcopy(record["before"]), record["data"])
        after = record["after"]
        where = (record["ts"], record["key"])
        assert got["status"]["name"] == after["status"]["name"], where
        assert (got.get("assignee") or {}).get("id") == (after.get("assignee") or {}).get("id"), where
        for key in ("estimatedHours", "actualHours"):
            assert got.get(key) == after.get(key), (where, key)
        for key in ("startDate", "dueDate"):
            assert (got.get(key) or "")[:10] == (after.get(key) or "")[:10], (where, key)
        sent = {int(k.split("_")[1]) for k in record["data"] if k.startswith("customField_")}
        got_fields = {f["id"]: f.get("value") for f in got["customFields"]}
        for field in after["customFields"]:
            if field["id"] in sent:
                assert display_value(got_fields[field["id"]]) == display_value(field.get("value")), (where, field["name"])
