#!/usr/bin/env python3
"""Holt einen eBay-User-Refresh-Token per OAuth (Authorization Code Grant).

Nur Standardbibliothek. Zwei Schritte:

  url        gibt die Consent-URL aus und öffnet sie im Browser
  exchange   liest die Redirect-URL von stdin, tauscht den Code gegen Tokens
             und gibt NUR den Refresh-Token auf stdout aus

Benötigte Variablen: EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, EBAY_REDIRECT_URI (RuName).
Optional: EBAY_OAUTH_SCOPES (Komma oder Leerzeichen getrennt).
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

AUTH_URL = "https://auth.ebay.com/oauth2/authorize"
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
DEFAULT_SCOPES = " ".join(
    "https://api.ebay.com/oauth/" + scope
    for scope in ("api_scope", "api_scope/sell.inventory", "api_scope/sell.account")
)
HTTP_TIMEOUT_SECONDS = 20
SECONDS_PER_DAY = 86400


class OAuthError(Exception):
    pass


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise OAuthError(f"Fehlende Umgebungsvariable: {name} (siehe README, Abschnitt Secrets)")
    return value


def scopes() -> str:
    raw = os.environ.get("EBAY_OAUTH_SCOPES", "").replace(",", " ").split()
    return " ".join(raw) if raw else DEFAULT_SCOPES


def consent_url() -> str:
    query = urllib.parse.urlencode({
        "client_id": require("EBAY_CLIENT_ID"),
        "redirect_uri": require("EBAY_REDIRECT_URI"),
        "response_type": "code",
        "scope": scopes(),
    })
    return f"{AUTH_URL}?{query}"


def extract_code(redirect_url: str) -> str:
    parsed = urllib.parse.urlparse(redirect_url.strip())
    for part in (parsed.query, parsed.fragment):
        values = urllib.parse.parse_qs(part).get("code")
        if values:
            return values[0]
    raise OAuthError("Kein Parameter „code“ in der eingefügten URL gefunden.")


def exchange_code(code: str) -> dict:
    client_id = require("EBAY_CLIENT_ID")
    client_secret = require("EBAY_CLIENT_SECRET")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": require("EBAY_REDIRECT_URI"),
    }).encode()
    request = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise OAuthError(
            f"Token-Tausch fehlgeschlagen (HTTP {exc.code}). Der Code ist nur wenige Minuten gültig "
            "und nur einmal verwendbar: Schritt „url“ wiederholen."
        ) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OAuthError(f"Netzwerkfehler bei eBay: {type(exc).__name__}") from None


def cmd_url(_args: argparse.Namespace) -> int:
    url = consent_url()
    print(url)
    print("Browser wird geöffnet. Nach der Zustimmung die komplette Adresse der "
          "Weiterleitungsseite kopieren und an „exchange“ übergeben.", file=sys.stderr)
    webbrowser.open(url)
    return 0


def cmd_exchange(args: argparse.Namespace) -> int:
    if sys.stdout.isatty() and not args.show:
        print(
            "Abbruch: Die Ausgabe ist ein Terminal, der Refresh-Token würde sichtbar. "
            "In den Secret-Manager pipen, zum Beispiel:\n"
            "  uv run python scripts/ebay_oauth.py exchange | doppler secrets set EBAY_USER_REFRESH_TOKEN --no-interactive --silent\n"
            "Oder bewusst mit --show anzeigen.",
            file=sys.stderr,
        )
        return 1
    if sys.stdin.isatty():
        print("Redirect-URL einfügen: ", end="", file=sys.stderr, flush=True)
    redirect_url = sys.stdin.readline()
    code = extract_code(redirect_url)
    tokens = exchange_code(code)
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise OAuthError("Antwort von eBay enthält keinen refresh_token.")
    try:
        days = int(tokens.get("refresh_token_expires_in", 0)) // SECONDS_PER_DAY
    except (TypeError, ValueError):
        days = 0
    print(refresh_token)
    print(f"Refresh-Token gültig für ca. {days} Tage.", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("url", help="Consent-URL ausgeben und im Browser öffnen").set_defaults(func=cmd_url)
    exchange = sub.add_parser("exchange", help="Redirect-URL von stdin lesen, Refresh-Token ausgeben")
    exchange.add_argument("--show", action="store_true", help="Token auch auf einem Terminal ausgeben")
    exchange.set_defaults(func=cmd_exchange)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except OAuthError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
