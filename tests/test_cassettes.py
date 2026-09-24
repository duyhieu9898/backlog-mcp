import os

from evals.cassettes import extract, rekey

SAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "legacy_telemetry_sample.jsonl")


def test_rekey():
    assert rekey("OOP-12762") == "OOP-912762"


def test_extract_keeps_latest_open_snapshot_patch_pairs_and_lists():
    cassette = extract(SAMPLE)
    assert list(cassette["issues"]) == ["OOP-912001"]
    assert cassette["issues"]["OOP-912001"]["status"]["name"] == "Open"
    assert cassette["issues"]["OOP-912001"]["summary"] == "[OOP-912000] Parent"
    [patch] = cassette["patches"]
    assert patch["key"] == "OOP-912001" and patch["data"] == {"statusId": 3, "assigneeId": 315996}
    assert patch["before"]["status"]["name"] == "Open" and patch["after"]["status"]["name"] == "Resolved"
    [listed] = cassette["lists"]
    assert listed["result"] == ["OOP-912002"] and listed["params"]["statusId[]"] == [1, 2, 3]


def test_extract_ignores_records_without_tool():
    assert "OOP-91" not in extract(SAMPLE)["issues"]
