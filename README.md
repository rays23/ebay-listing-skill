# ebay-listing-skill

Eine Claude-Code-Skill für deutsche eBay.de-Verkäufer: Du gibst ein oder mehrere Fotos eines Artikels, Claude erkennt ihn, wählt Kategorie, Artikelmerkmale, Zustand und Versandprofil, schlägt anhand aktiver Vergleichsangebote einen Preis vor und zeigt dir eine kompakte Vorschau. Nach einem einzigen „ja“ ist das Angebot als Festpreisangebot (mit Preisvorschlag) live, und die Skill gibt dir den Link.

Der Aufruf sieht so aus:

```
/ebay-einstellen ~/Fotos/ssd-vorne.jpg ~/Fotos/ssd-hinten.jpg
```

Und das ist die Vorschau (Beispiel mit erfundenen Zahlen), auf die du mit „ja“, „nein“ oder einer Korrektur wie „Preis 40“ antwortest:

```
Titel:      Sabrent Rocket NVMe 4.0 1 TB M.2 2280 interne SSD
Zustand:    Gebraucht – keine sichtbaren Mängel, Etikett leicht zerkratzt
Kategorie:  Computer, Tablets & Netzwerk > Laufwerke & Speichermedien > Solid State Drives
Preis:      79 € (Preisvorschlag, Auto-Annahme ab 67 €)
Basis:      "Sabrent Rocket NVMe 4.0 1TB" · 6 passende von 31 Angeboten · Median 72,50 € · Neupreis 119 € (Deckel: nein)
Versand:    Versand S – DHL Päckchen S (S)
Warnungen:  Seriennummer auf Foto 2 lesbar
Einstellen? (ja / nein / Korrektur, z. B. "Preis 40")
```

## Voraussetzungen

- [Claude Code](https://claude.com/claude-code)
- Node.js (für den eBay-MCP-Server) und npm
- [uv](https://docs.astral.sh/uv/) und Python 3.13 (für die Preisberechnung)
- Ein eBay-Konto, mit dem du verkaufst, und ein eBay-Developer-Account (kostenlos)
- Optional: die [Firecrawl-CLI](https://www.firecrawl.dev/) für den Neupreis-Deckel (idealo-Preisvergleich). Ohne sie entfällt der Deckel, der Rest funktioniert.

## Einrichtung

Das Setup dauert einmalig etwa eine Stunde. Die meisten Schritte sind Klicks im eBay-Developer-Portal.

### 1. Developer-Account und Production-Keyset

1. Auf [developer.ebay.com](https://developer.ebay.com) mit dem eBay-Konto registrieren, über das du verkaufst (Typ „Individual“ reicht).
2. Im Developer-Portal unter „Application Keysets“ ein **Production**-Keyset anlegen, App-Name frei wählbar.
3. **App ID (Client ID)** und **Cert ID (Client Secret)** notieren. Beide sind Secrets, siehe Abschnitt „Secrets“.

### 2. Marketplace Account Deletion: Opt-out

Neue Keysets verlangen eine Entscheidung zu den „Marketplace Account Deletion Notifications“. Wähle **Opt-out** mit der Begründung „does not persist eBay user data“: Die Skill speichert keine eBay-Nutzerdaten, ein Benachrichtigungs-Endpunkt ist deshalb nicht nötig.

### 3. RuName (Redirect) anlegen

Im Developer-Portal beim Keyset unter „User Tokens“ den Link „Get a Token from eBay via Your Application“ öffnen und einen **RuName** anlegen. Lass bei „Your auth accepted URL“ die Vorgabe von eBay stehen (eine eBay-Dankesseite). Du brauchst keinen eigenen Server: Nach der Zustimmung steht der Code in der Adresszeile dieser Dankesseite (siehe Schritt 5). Notiere den RuName (sieht aus wie `Name-AppName-xxxxxx-abcdefg`).

### 4. Secrets ablegen

Lege die Variablen aus dem Abschnitt „Secrets“ in deinem Secret-Manager ab. Jetzt brauchst du erst `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `EBAY_REDIRECT_URI`, `EBAY_ENVIRONMENT`, `EBAY_MARKETPLACE_ID`, `EBAY_CONTENT_LANGUAGE`, `EBAY_OAUTH_SCOPES` und `EBAY_MCP_TOOLS`. Den Refresh-Token holst du im nächsten Schritt.

### 5. OAuth-Token holen

Die Scopes sind bewusst begrenzt auf `api_scope`, `sell.inventory` und `sell.account` (siehe `docs/ebay-mcp-review.md`). Das Skript `scripts/ebay_oauth.py` baut die Consent-URL mit genau diesen Scopes. Starte die Befehle aus einer Shell, in der die Variablen gesetzt sind (Beispiel mit Doppler):

```bash
doppler run -- uv run python scripts/ebay_oauth.py url
```

Der Browser öffnet die eBay-Zustimmungsseite. Melde dich an und stimme zu. Danach landest du auf einer Dankesseite von eBay. **Kopiere die komplette Adresse aus der Adresszeile** (sie enthält `code=...`). Der Code ist nur wenige Minuten gültig und nur einmal verwendbar.

```bash
doppler run -- uv run python scripts/ebay_oauth.py exchange | doppler secrets set EBAY_USER_REFRESH_TOKEN --no-interactive --silent
```

Das Skript fragt nach der kopierten Adresse, tauscht den Code gegen Tokens und gibt **nur den Refresh-Token** auf stdout aus, die Restlaufzeit steht auf stderr. Läuft stdout auf einem Terminal, bricht das Skript ab (außer mit `--show`), damit der Token nicht versehentlich im Terminal landet. Der Refresh-Token gilt etwa 18 Monate. Danach wiederholst du diesen Schritt.

### 6. Business Policies aktivieren (Opt-in)

Die Inventory API verlangt das Opt-in in das Programm `SELLING_POLICY_MANAGEMENT` (Business Policies). Das erledigst du in Claude Code mit den MCP-Tools (nach Schritt 10): `mcp__ebay__ebay_opt_in_to_program` mit `{"programType": "SELLING_POLICY_MANAGEMENT"}`, danach `mcp__ebay__ebay_get_opted_in_programs` zur Kontrolle. Die Freischaltung kann einige Minuten dauern. Ein Privatkonto ist laut eBay-Doku kein Hindernis, ein Test mit einem echten Artikel hat das bestätigt.

### 7. Zahlungs-, Rückgabe- und Versandprofile anlegen

Bitte Claude, sie über die MCP-Tools anzulegen, oder lege sie in „Mein eBay“ unter den Verkaufseinstellungen an. Du brauchst:

- **Zahlungs-Policy:** eBay-Zahlungsabwicklung ohne eigene Zahlungsarten. Existiert schon eine, nimm sie (`mcp__ebay__ebay_get_payment_policies`).
- **Rückgabe-Policy:** für Privatverkäufe „keine Rücknahme“ (`returnsAccepted: false`, Kategorie-Typ `ALL_EXCLUDING_MOTORS_VEHICLES`).
- **Sechs Versandprofile S bis XXXL.** Beispiel mit DHL-Pauschalen (Käufer zahlt, Bearbeitungszeit 2 Tage, Beträge sind ein Beispiel, prüfe die aktuelle DHL-Preisliste): Päckchen S 4,49 €, Päckchen M 5,49 €, Paket bis 5 kg 7,99 €, bis 10 kg 10,99 €, bis 20 kg 19,49 €, bis 31,5 kg 24,49 €. Auf eBay.de gibt es für DHL nur Pauschalen (`FLAT_RATE`), keine berechneten Versandkosten. Gültige Service-Codes liefert `mcp__ebay__ebay_get_shipping_services` mit `marketplaceId: EBAY_DE`; erfundene Codes lehnt eBay ab.

### 8. Lagerort anlegen

`mcp__ebay__ebay_create_inventory_location` mit einem Schlüssel (z. B. `home`), Land `DE`, deiner PLZ und deinem Ort, Typ `WAREHOUSE`.

### 9. `config/listing-defaults.json` befüllen

```bash
cp config/listing-defaults.example.json config/listing-defaults.json
```

Trage die IDs der Policies und den Lagerort-Schlüssel ein (IDs sind keine Secrets, die Datei ist trotzdem in `.gitignore`). `insuredShippingFromEur` (Standard 100) steuert: Ab diesem Preis wählt die Skill bei den Klassen S und M stattdessen L, weil ein DHL Päckchen nicht versichert ist.

### 10. Abhängigkeiten installieren und MCP-Server einbinden

```bash
npm ci
ls -la node_modules/ebay-mcp/
uv sync
cp .mcp.json.example .mcp.json
```

Prüfe nach `npm ci`, dass die Ausgabe von `ls -la` die Zeile `.env -> /dev/null` enthält (der `postinstall`-Schritt legt diesen Symlink an, Begründung im Abschnitt „Secrets“). In `.mcp.json` ersetzt du `<ABSOLUTER_PFAD>` durch den absoluten Pfad dieses Ordners, denn `ebay-mcp` akzeptiert für `EBAY_MCP_MEDIA_DIRS` nur absolute Pfade.

Starte Claude Code aus einer Shell, die die Variablen gesetzt hat (siehe „Secrets“), im Repo-Ordner, und gib den Server `ebay` frei. `/mcp` muss ihn als verbunden zeigen. Dann führst du die Schritte 6 bis 8 aus, sofern noch nicht geschehen.

## Secrets

Alle Zugangsdaten kommen aus der **Umgebung** von Claude Code. Der MCP-Server und das Preismodul erben sie.

| Variable | Bedeutung |
|---|---|
| `EBAY_CLIENT_ID` | App ID (Client ID) des Production-Keysets |
| `EBAY_CLIENT_SECRET` | Cert ID (Client Secret) des Production-Keysets |
| `EBAY_REDIRECT_URI` | der RuName aus Schritt 3 |
| `EBAY_USER_REFRESH_TOKEN` | Refresh-Token aus Schritt 5, ca. 18 Monate gültig |
| `EBAY_ENVIRONMENT` | `production`. Der Standard von `ebay-mcp` ist Sandbox |
| `EBAY_MARKETPLACE_ID` | `EBAY_DE` (Standard von `ebay-mcp` ist `EBAY_US`) |
| `EBAY_CONTENT_LANGUAGE` | `de-DE` (Standard ist `en-US`) |
| `EBAY_OAUTH_SCOPES` | `https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/sell.account`, begrenzt die Rechte der Consent-URL |
| `EBAY_MCP_TOOLS` | `inventory,taxonomy,metadata,account,browse`. Ohne diese Einschränkung wären alle 384 Tools aktiv, auch Löschen von Bestellungen, Marketing und Finanzen |

**Empfehlung:** Nutze einen Secret-Manager, zum Beispiel [Doppler](https://www.doppler.com/), die 1Password-CLI oder die macOS-Keychain, und starte Claude Code über ihn:

```bash
doppler run -- claude
```

Der Server `ebay` und `uv run python -m pricing` erben die Variablen aus dieser Shell. Die Skill ruft nirgends selbst einen Secret-Manager auf.

**Keine `.env`-Dateien.** `ebay-mcp` liest ohnehin keine `.env` aus deinem Projekt, schreibt aber bei jedem Token-Refresh Access-Tokens im Klartext nach `node_modules/ebay-mcp/.env`. Der `postinstall`-Schritt in `package.json` ersetzt diese Datei deshalb durch einen Symlink auf `/dev/null`: Schreiben und Lesen laufen ins Leere, nichts bleibt auf der Platte. Nach jedem `npm install` oder `npm ci` läuft der Schritt automatisch. Die Skill prüft vor dem ersten schreibenden Aufruf zusätzlich, dass der Symlink noch da ist.

## Nutzung

Starte Claude Code im Repo-Ordner (mit gesetzten Variablen) und rufe auf:

```
/ebay-einstellen foto1.jpg foto2.jpg
```

Claude sieht sich die Fotos an, stellt bei Unsicherheit **eine** Rückfrage (z. B. „XM4 oder XM5?“), holt Kategorie, Pflichtmerkmale und Zustand, ermittelt den Preis und zeigt die Vorschau. Antworte mit „ja“, „nein“ oder einer Korrektur („Preis 40“). Nach „ja“ lädt die Skill die Fotos hoch, legt Artikel und Angebot an, veröffentlicht und gibt `Live: https://www.ebay.de/itm/<listingId>` aus. Ein zweites „ja“ oder ein Neuversuch in derselben Sitzung erzeugt kein zweites Angebot: Die SKU wird pro Lauf einmal erzeugt (Datum plus Hash des ersten Fotopfads), ein vorhandenes Angebot zur SKU wird aktualisiert. Startest du an einem anderen Tag neu, entsteht eine neue SKU, prüfe dann vorher „Mein eBay“.

## Preislogik (kurz)

Das Python-Paket `pricing` (reine Funktionen, getestet mit `uv run pytest`) rechnet:

1. Aktive Festpreisangebote aus der eBay Browse API (EBAY_DE, Artikelstandort DE, passende Kategorie und Zustand).
2. **Titelfilter:** Alle Wörter des Suchbegriffs müssen im Titel stehen (Bindestriche und Leerzeichen egal), `--exclude`-Wörter dürfen nicht als ganzes Wort vorkommen. Das filtert Geschwistervarianten und Zubehör heraus, die die lose Suche von eBay mitliefert.
3. Ausreißer fallen per IQR-Filter raus (1,5 × IQR).
4. Median × 0,90 (Angebotspreise liegen über echten Verkaufspreisen), gedeckelt bei 70 % des Neupreises, dann × 1,10 als Spielraum für Preisvorschläge. Auto-Annahme ab 85 % des Angebotspreises.
5. Weniger als drei passende Angebote ergeben `NO_COMPS` (Exit-Code 2): Die Skill lockert die Suche einmal, danach fragt sie dich nach einem Preis, statt zu raten.

Alle Schwellenwerte stehen in `pricing/config.py`. Verkaufte Artikel kann die Skill nicht auswerten, weil eBay die Suche danach nur eingeloggten Nutzern zeigt.

## Grenzen

- Nur **Festpreis** (mit Preisvorschlag), keine Auktionen.
- Nur **eBay.de**.
- Für **Privatverkäufe**: keine Rücknahme, keine Garantie, kein gewerbliches Konto.
- **Keine Abholung** und nichts über 31,5 kg oder Sperrgut über 120 × 60 × 60 cm.
- HEIC-Fotos (iPhone) sind **ungetestet**: Scheitert der Upload, versucht die Skill eine Konvertierung per `sips` (macOS).
- Keine Verwaltung nach dem Einstellen (Preis senken, Nachrichten, Versandlabel).

## Kosten

- Die eBay-APIs sind kostenlos. Für Angebote und Verkäufe gelten die üblichen eBay-Gebühren, prüfe sie in deinem Konto.
- Du brauchst ein Claude-Code-Abo oder API-Guthaben für die Bilderkennung und den Ablauf.
- Firecrawl (optional, Neupreis) hat ein eigenes Kontingent, ein Aufruf pro Artikel.

## Sicherheit

Das eingesetzte Paket `ebay-mcp` ist exakt auf 1.18.0 gepinnt, das Lockfile pinnt auch alle Unterabhängigkeiten. Der Sicherheitsreview mit Netzwerkzielen, Schreibzugriffen, Scopes und Auflagen steht in [docs/ebay-mcp-review.md](docs/ebay-mcp-review.md). Die Skill veröffentlicht nie ohne dein ausdrückliches „ja“ in derselben Vorschau-Runde.

## Lizenz

[GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0-only). Copyright (C) 2026 die Autoren von ebay-listing-skill.
