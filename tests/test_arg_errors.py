from pydantic import BaseModel, ConfigDict, ValidationError

from backlog_mcp.arg_errors import describe_validation_error


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue_key: str
    limit: int = 10


def error_for(payload):
    try:
        Args(**payload)
    except ValidationError as error:
        return error
    raise AssertionError("expected ValidationError")


def test_unknown_missing_invalid_and_suggestions():
    details = describe_validation_error(
        error_for({"issueKey": "OOP-1", "limt": "x"}),
        ["issue_key", "limit"],
    )
    assert details["unknown"] == ["issueKey", "limt"]
    assert details["missingRequired"] == ["issue_key"]
    assert details["suggested"] == {"issueKey": "issue_key", "limt": "limit"}
    assert details["invalid"] == []


def test_invalid_type_is_reported():
    details = describe_validation_error(error_for({"issue_key": "OOP-1", "limit": "abc"}), ["issue_key", "limit"])
    assert details["invalid"] == [{"name": "limit", "reason": "int_parsing"}]
    assert details["unknown"] == [] and details["suggested"] == {}


def test_no_suggestion_for_unrelated_name():
    details = describe_validation_error(error_for({"issue_key": "OOP-1", "zzzz": 1}), ["issue_key", "limit"])
    assert details["suggested"] == {}
