import pytest

from scripts import ebay_oauth


def test_extract_code_from_query():
    url = "https://signin.ebay.de/ths?code=v%5E1.1%23abc&expires_in=299"
    assert ebay_oauth.extract_code(url) == "v^1.1#abc"


def test_extract_code_from_fragment():
    assert ebay_oauth.extract_code("https://localhost/#code=xyz") == "xyz"


def test_extract_code_missing_raises():
    with pytest.raises(ebay_oauth.OAuthError):
        ebay_oauth.extract_code("https://localhost/?error=declined")


def test_scopes_default_and_override(monkeypatch):
    monkeypatch.delenv("EBAY_OAUTH_SCOPES", raising=False)
    assert ebay_oauth.scopes() == ebay_oauth.DEFAULT_SCOPES
    monkeypatch.setenv("EBAY_OAUTH_SCOPES", "a,b c")
    assert ebay_oauth.scopes() == "a b c"


def test_consent_url_requires_config(monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    with pytest.raises(ebay_oauth.OAuthError):
        ebay_oauth.consent_url()


class _FakeStdin:
    def __init__(self, line: str, tty: bool) -> None:
        self._line = line
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty

    def readline(self) -> str:
        return self._line


def test_exchange_writes_only_token_to_stdout(monkeypatch, capsys):
    monkeypatch.setattr(ebay_oauth.sys, "stdin", _FakeStdin("https://x/?code=abc\n", tty=True))
    monkeypatch.setattr(ebay_oauth, "exchange_code", lambda code: {"refresh_token": "tok-" + code, "refresh_token_expires_in": 86400 * 3})
    assert ebay_oauth.main(["exchange"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "tok-abc\n"
    assert "Redirect-URL" in captured.err
