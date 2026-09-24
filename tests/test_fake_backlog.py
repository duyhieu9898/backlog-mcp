import requests

from evals.fake_backlog import SCENARIO_KEYS, SCENARIO_OPEN, FakeBacklog, apply_patch, build_issues, matches_list

ME = 778617


def test_synthetic_issues_cover_scenarios():
    issues = build_issues(source="synthetic")
    assert sorted(issues) == sorted(SCENARIO_KEYS)
    open_keys = sorted(k for k, i in issues.items() if i["assignee"]["id"] == ME and i["status"]["name"] != "Resolved")
    assert open_keys == sorted(SCENARIO_OPEN)
    role = {c["name"]: c["value"] for c in issues["OOP-912749"]["customFields"]}["Detected Role"]
    assert role["name"] == "Developer"
    assert issues["OOP-912744"]["attachments"][0]["name"] == "login-error.png"


def test_no_open_bugs_state():
    issues = build_issues(state="no_open_bugs", source="synthetic")
    assert not [i for i in issues.values() if i["assignee"]["id"] == ME]


def test_apply_patch_and_list_filter():
    issue = build_issues(source="synthetic")["OOP-912762"]
    patched = apply_patch(issue, {"statusId": 3, "assigneeId": 315996, "startDate": "2026-09-23", "estimatedHours": 1, "customField_9866": "no", "customField_9864": 1})
    assert patched["status"]["name"] == "Resolved" and patched["assignee"]["id"] == 315996
    assert patched["startDate"] == "2026-09-23T00:00:00Z" and patched["estimatedHours"] == 1
    values = {c["id"]: c["value"] for c in patched["customFields"]}
    assert values[9866] == "no" and values[9864]["name"] == "Integration Test"
    assert not matches_list(patched, {"assigneeId[]": [ME], "statusId[]": [1, 2, 3]})
    assert matches_list(patched, {"assigneeId[]": ["315996"]})


def test_http_endpoints_and_unhandled():
    with FakeBacklog(source="synthetic") as fake:
        base = fake.base_url + "/api/v2"
        assert requests.get(f"{base}/issues/OOP-912762", params={"apiKey": "k"}).json()["issueKey"] == "OOP-912762"
        listed = requests.get(f"{base}/issues", params={"apiKey": "k", "assigneeId[]": ME, "statusId[]": [1, 2, 3], "count": 50}).json()
        assert sorted(i["issueKey"] for i in listed) == sorted(SCENARIO_OPEN)
        patched = requests.patch(f"{base}/issues/OOP-912762", params={"apiKey": "k"}, data={"statusId": 3, "assigneeId": 315996}).json()
        assert patched["status"]["name"] == "Resolved"
        assert fake.patches == [{"key": "OOP-912762", "form": {"statusId": ["3"], "assigneeId": ["315996"]}}]
        assert requests.get(f"{base}/issues/OOP-1", params={"apiKey": "k"}).status_code == 404
        assert requests.get(f"{base}/space", params={"apiKey": "k"}).status_code == 404
        assert fake.unhandled == [{"method": "GET", "path": "/api/v2/space"}]


def test_apply_patch_assignee_to_reporter_carries_name():
    issue = build_issues(source="synthetic")["OOP-912762"]
    reporter = issue["createdUser"]
    patched = apply_patch(issue, {"assigneeId": reporter["id"]})
    assert patched["assignee"]["id"] == reporter["id"] and patched["assignee"]["name"] == reporter["name"]
