from unittest.mock import sentinel

import pytest

from celofast import client


def test_get_celonis_uses_oauth_credentials(monkeypatch):
    monkeypatch.setenv("CELONIS_URL", "https://example.celonis.cloud/")
    monkeypatch.setenv("OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OAUTH_SCOPES", "studio integration.data-pools")
    client.get_celonis.cache_clear()

    oauth_calls = []
    client_calls = []

    def fake_oauth2(client_id, client_secret, scopes):
        oauth_calls.append((client_id, client_secret, scopes))
        return sentinel.oauth_callback

    def fake_get_celonis(**kwargs):
        client_calls.append(kwargs)
        return sentinel.celonis

    monkeypatch.setattr(client, "oauth2", fake_oauth2)
    monkeypatch.setattr(client, "pycelonis_get_celonis", fake_get_celonis)

    assert client.get_celonis() is sentinel.celonis
    assert oauth_calls == [
        ("client-id", "client-secret", "studio integration.data-pools")
    ]
    assert client_calls == [
        {
            "base_url": "https://example.celonis.cloud",
            "api_token": sentinel.oauth_callback,
            "key_type": client.KeyType.BEARER,
            "user_agent": "celofast",
            "verify_ssl": True,
            "check_if_outdated": False,
            "permissions": False,
        }
    ]
    client.get_celonis.cache_clear()


def test_get_celonis_reports_missing_oauth_configuration(monkeypatch):
    monkeypatch.setenv("CELONIS_URL", "https://example.celonis.cloud")
    monkeypatch.delenv("OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OAUTH_SCOPES", raising=False)
    client.get_celonis.cache_clear()

    with pytest.raises(RuntimeError, match="OAUTH_CLIENT_ID"):
        client.get_celonis()

    client.get_celonis.cache_clear()
