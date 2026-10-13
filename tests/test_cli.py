import json

import httpx

from pricing.__main__ import main

ENV = {"EBAY_CLIENT_ID": "id", "EBAY_CLIENT_SECRET": "pw"}


def _client(prices, title="Sony WH-1000XM4"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        items = [{"title": title, "price": {"value": str(p), "currency": "EUR"}} for p in prices]
        return httpx.Response(200, json={"itemSummaries": items})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_success_outputs_json(capsys):
    code = main(["--query", "sony", "--category-id", "112529", "--new-price", "500"], ENV, _client([100] * 6))
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["listing_price"] == 99
    assert out["query"] == "sony"
    assert out["category_id"] == "112529"
    assert out["new_price"] == 500.0
    assert out["warnings"] == []
    assert out["candidate_count"] == 6
    assert out["active_count"] == 6


def test_exclude_is_passed_through(capsys):
    code = main(["--query", "sony", "--category-id", "1", "--exclude", "wh"], ENV, _client([100] * 6))
    assert code == 2
    assert "NO_COMPS" in capsys.readouterr().err


def test_exclude_can_repeat_and_second_value_applies(capsys):
    kept = main(["--query", "sony", "--category-id", "1", "--exclude", "bose"], ENV, _client([100] * 6))
    capsys.readouterr()
    dropped = main(["--query", "sony", "--category-id", "1", "--exclude", "bose", "--exclude", "wh"], ENV, _client([100] * 6))
    assert kept == 0
    assert dropped == 2


def test_no_comps_exit_2(capsys):
    code = main(["--query", "sony", "--category-id", "1"], ENV, _client([100]))
    assert code == 2
    assert "NO_COMPS" in capsys.readouterr().err


def test_missing_client_id_exit_1_without_leak(capsys):
    code = main(["--query", "sony", "--category-id", "1"], {"EBAY_CLIENT_SECRET": "do-not-leak"}, _client([100] * 6))
    err = capsys.readouterr().err
    assert code == 1
    assert "Fehlende Umgebungsvariablen" in err
    assert "EBAY_CLIENT_ID" in err
    assert "README" in err
    assert "do-not-leak" not in err


def test_api_error_exit_1(capsys):
    def handler(request):
        return httpx.Response(503)

    code = main(["--query", "sony", "--category-id", "1"], ENV, httpx.Client(transport=httpx.MockTransport(handler)))
    assert code == 1
    assert "HTTP 503" in capsys.readouterr().err


def test_network_error_exit_1(capsys):
    def handler(request):
        raise httpx.ConnectError("boom")

    code = main(["--query", "sony", "--category-id", "1"], ENV, httpx.Client(transport=httpx.MockTransport(handler)))
    assert code == 1
    assert "Netzwerkfehler" in capsys.readouterr().err


def test_malformed_token_response_exit_1(capsys):
    def handler(request):
        return httpx.Response(200, json={})

    code = main(["--query", "sony", "--category-id", "1"], ENV, httpx.Client(transport=httpx.MockTransport(handler)))
    assert code == 1
    assert "Unerwartete Antwort" in capsys.readouterr().err
