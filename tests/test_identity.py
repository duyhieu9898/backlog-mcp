from unittest import mock

import pytest

from backlog_tool import settings

CONFIG = {"base_url": "https://space.backlog.com", "projects": ["OOP"]}


@pytest.fixture(autouse=True)
def fresh_identity_cache(monkeypatch):
    monkeypatch.setattr(settings, "_CURRENT_USERS", {})
    monkeypatch.setenv("BACKLOG_API_KEY", "key-a")


def test_me_is_the_owner_of_the_api_key_fetched_once():
    client = mock.Mock()
    client.request_json.return_value = {"id": 42, "name": "Dev"}
    with mock.patch("backlog_tool.client.BacklogClient", return_value=client):
        assert settings.resolve_user_id(CONFIG, "me") == 42
        assert settings.resolve_user_id(CONFIG, "me") == 42
    client.request_json.assert_called_once_with("GET", "/users/myself")


def test_another_api_key_is_another_user(monkeypatch):
    client = mock.Mock()
    client.request_json.side_effect = [{"id": 1}, {"id": 2}]
    with mock.patch("backlog_tool.client.BacklogClient", return_value=client):
        assert settings.resolve_user_id(CONFIG, "me") == 1
        monkeypatch.setenv("BACKLOG_API_KEY", "key-b")
        assert settings.resolve_user_id(CONFIG, "me") == 2


def test_configured_user_overrides_the_api_lookup():
    config = {**CONFIG, "users": {"me": {"id": 7}}}
    with mock.patch("backlog_tool.client.BacklogClient") as client:
        assert settings.resolve_user_id(config, "me") == 7
    client.assert_not_called()


def test_unknown_user_reference_fails():
    with pytest.raises(ValueError, match="Unknown Backlog user reference 'tam'"):
        settings.resolve_user_id(CONFIG, "tam")


def test_base_url_comes_from_env(monkeypatch):
    monkeypatch.setattr(settings, "load_env_file", lambda: None)
    monkeypatch.setenv("BACKLOG_BASE_URL", "https://space.backlog.com")
    assert settings.load_config()["base_url"] == "https://space.backlog.com"


def test_missing_base_url_names_the_env_variable(monkeypatch):
    monkeypatch.setattr(settings, "load_env_file", lambda: None)
    monkeypatch.delenv("BACKLOG_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="BACKLOG_BASE_URL"):
        settings.load_config()
