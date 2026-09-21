import unittest
from unittest import mock
import requests

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backlog_tool import client as backlog_client


class FakeResponse:
    ok = True
    status_code = 200
    text = ""

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeErrorResponse(FakeResponse):
    ok = False
    status_code = 400
    text = '{"errors":[{"message":"bad request"}]}'

    def raise_for_status(self):
        raise requests.HTTPError("400 Client Error: Bad Request for url: https://example.backlog.com/api/v2/issues?apiKey=secret")


class BacklogClientTest(unittest.TestCase):
    def test_request_json_adds_api_key_timeout_and_logs_path_only(self):
        config = {"base_url": "https://example.backlog.com"}
        response = FakeResponse({"ok": True})

        with mock.patch.object(backlog_client, "require_api_key", return_value="test-key"), mock.patch.object(
            backlog_client.requests,
            "request",
            return_value=response,
        ) as request, mock.patch.object(backlog_client, "log_response") as log_response:
            result = backlog_client.BacklogClient(config).request_json(
                "GET",
                "/issues",
                params={"count": 100},
            )

        self.assertEqual({"ok": True}, result)
        request.assert_called_once_with(
            "GET",
            "https://example.backlog.com/api/v2/issues",
            params={"apiKey": "test-key", "count": 100},
            data=None,
            timeout=20,
        )
        log_response.assert_called_once_with("GET", "/issues", response)

    def test_get_issues_builds_backlog_list_params(self):
        client = backlog_client.BacklogClient({"base_url": "https://example.backlog.com"})

        with mock.patch.object(client, "request_json", return_value=[]) as request_json:
            result = client.get_issues(82531, query="bug", assignee_id=778617)

        self.assertEqual([], result)
        request_json.assert_called_once_with(
            "GET",
            "/issues",
            params={
                "projectId[]": [82531],
                "count": 100,
                "offset": 0,
                "keyword": "bug",
                "assigneeId[]": [778617],
            },
        )

    def test_request_json_raises_sanitized_error_without_api_key_url(self):
        config = {"base_url": "https://example.backlog.com"}

        with mock.patch.object(backlog_client, "require_api_key", return_value="test-key"), mock.patch.object(
            backlog_client.requests,
            "request",
            return_value=FakeErrorResponse({}),
        ), mock.patch.object(backlog_client, "log_response"):
            with self.assertRaisesRegex(RuntimeError, "POST /issues failed with status 400") as raised:
                backlog_client.BacklogClient(config).request_json("POST", "/issues")

        self.assertNotIn("apiKey", str(raised.exception))
        self.assertNotIn("test-key", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
