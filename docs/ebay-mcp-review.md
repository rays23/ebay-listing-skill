# Sicherheitsreview ebay-mcp 1.18.0

Stand: 2026-10-02. Geprüft wurde das installierte Paket `node_modules/ebay-mcp` (exakt gepinnt, `package.json`: `"ebay-mcp": "1.18.0"`, `package-lock.json` eingecheckt). Methode: Grep und Lektüre des kompilierten Codes in `build/`, kein Start des Servers, keine eBay-Credentials im Spiel.

## Urteil

Brauchbar mit Auflagen. Es gibt keinen Hinweis auf Exfiltration, versteckte Hosts oder Code-Ausführung im Laufzeitpfad. Aber zwei Punkte weichen von der Erwartung ab:

1. **Der Laufzeit-Server schreibt Tokens auf Platte.** Bei jedem Token-Refresh landen `EBAY_USER_ACCESS_TOKEN` und `EBAY_APP_ACCESS_TOKEN` im Klartext in `node_modules/ebay-mcp/.env`. Erwartet war Schreibzugriffe nur im Setup-Assistenten.
2. **Der Server fragt zur Laufzeit `registry.npmjs.org` ab** (update-notifier), sofern `NO_UPDATE_NOTIFIER=1` nicht gesetzt ist. Das ist wie erwartet und ist in `.mcp.json` abgeschaltet.

Die übrigen Erwartungen (Netzwerkziele, kein `child_process` im Laufzeitpfad, `npm audit`) sind erfüllt.

## 1. Netzwerkziele

Alle URLs im Build (`grep -rhoE "https?://..."`), nach Nutzung gruppiert:

| Host | Nutzung |
|---|---|
| `api.ebay.com`, `apiz.ebay.com`, `apim.ebay.com`, `svcs.ebay.com` | Laufzeit: eBay-APIs, `getBaseUrl` wählt je nach `EBAY_ENVIRONMENT` |
| `auth.ebay.com`, `signin.ebay.com` | OAuth-Consent-URL (nur Token-Management-Tools und Setup) |
| `api.sandbox.ebay.com`, `apiz.sandbox.ebay.com`, `apim.sandbox.ebay.com`, `svcs.sandbox.ebay.com`, `auth.sandbox.ebay.com`, `signin.sandbox.ebay.com` | Sandbox-Pendants, bei `EBAY_ENVIRONMENT=production` ungenutzt |
| `developer.ebay.com` | überwiegend Doku-Links in Kommentaren und Tool-Beschreibungen; Laufzeit nur `https://developer.ebay.com/rss/api-status` im Developer-Tool (`utils/apiStatusFeed.js`, nur auf Aufruf) |
| `www.ebay.<tld>`, `info.ebay.co.th` | Marktplatz-Tabelle, keine Requests |
| `registry.npmjs.org` | indirekt über `update-notifier` (siehe unten), taucht nicht als Literal im Build auf |
| `localhost` | lokaler OAuth-Callback im Setup (`auth/oauthHelper.js`, Port aus `EBAY_REDIRECT_URI` oder `EBAY_OAUTH_CALLBACK_PORT`), nur Setup |
| `github.com`, `www.linkedin.com`, `nodejs.org`, `react.dev`, `www.w3.org`, `json-schema.org`, `example.com`, `your-domain.com`, `your-redirect-uri` | Doku-, Autoren- und Schema-Links bzw. Platzhalter, keine Requests |

Befund: kein fremder Host, an den Daten gesendet werden. Es gibt die Override-Variable `EBAY_MCP_API_BASE_URL`, die die eBay-Basis-URL ersetzt. Sie wird nur aus der Umgebung gelesen, wir setzen sie nicht. Kein Drittanbieter-Telemetrie-Code gefunden.

**update-notifier:** `index.js` ruft beim Start `getCachedUpdateNotice()` auf. Das erzeugt einen `updateNotifier` und löst im Hintergrund höchstens einmal täglich einen Registry-Abruf aus; update-notifier schreibt dabei einen Cache nach `~/.config/configstore/`. `NO_UPDATE_NOTIFIER=1` (steht in `.mcp.json`) schaltet das ab.

## 2. Schreibzugriffe auf Platte

### Setup-Pfad (nicht benutzt)
`scripts/setup.js`, `setupWizard.js`, `interactiveSetup.js`, `autoSetup.js` schreiben `.env` und Client-Konfigurationen. `scripts/devSync.js` und `scripts/securityChecker.js` sind Entwickler-Werkzeuge. Wir rufen keines davon auf. Der Server-Einstieg `build/index.js` leitet nur bei CLI-Argumenten (`setup`, `diagnose`, `skills`) dorthin.

### Laufzeit-Pfad (stdio-Server) – ABWEICHUNG VON DER ERWARTUNG
`auth/credentialSession.js`, Klasse `DotEnvCredentialStore.write()`: liest die Datei `CREDENTIAL_ENV_PATH`, mischt die Updates ein und schreibt per `writeFileSync` zurück, danach `fsync`. Der Pfad ist per `config/credentialFile.js` fest: `<Paketwurzel>/.env`, also **`node_modules/ebay-mcp/.env`**. Er ist nicht konfigurierbar und unabhängig von `process.cwd()`. Dateimodus: Standard-umask, kein `chmod 600`.

Aufrufer (`auth/oauth.js`):

| Auslöser | Geschriebene Variablen |
|---|---|
| `initialize()` beim Start, wenn `EBAY_USER_REFRESH_TOKEN` gesetzt ist: `refreshUserToken()` | `EBAY_USER_ACCESS_TOKEN` |
| `refreshUserToken()` bei jedem Refresh (alle ca. 2 Stunden) | `EBAY_USER_ACCESS_TOKEN`; zusätzlich `EBAY_USER_REFRESH_TOKEN`, **nur falls** der Wert vom Config-Wert abweicht |
| `getOrRefreshAppAccessToken()` (Client-Credentials-Token, direkt nach dem Start und bei Ablauf) | `EBAY_APP_ACCESS_TOKEN` |
| Token-Management-Tools (`ebay_set_user_tokens*`, Code-Exchange) | alle Token-Variablen |

Zum Refresh-Token: eBay rotiert Refresh-Tokens beim Refresh normalerweise nicht. Der Code übernimmt `tokenData.refresh_token ?? previousTokens.userRefreshToken` (`createStoredUserTokensFromResponse`). Solange eBay kein neues Refresh-Token liefert, bleibt es gleich dem Doppler-Wert und wird nicht geschrieben. Liefert eBay doch ein neues, würde es im Klartext in der `.env` landen, während der Secret-Manager den alten Wert behält.

Weitere Beobachtungen:
- Die `.env` existierte zum Reviewzeitpunkt nicht (`ls node_modules/ebay-mcp/.env` – nicht vorhanden). Sie entsteht erst beim ersten Serverstart mit Credentials.
- Beim Start lädt `config/environment.js` die Datei per `dotenv` (`config({ path: CREDENTIAL_ENV_PATH })`). dotenv überschreibt vorhandene Umgebungsvariablen nicht. Werte aus der Umgebung haben daher Vorrang. Es wird **keine** `.env` aus dem cwd gelesen, nur die im Paketverzeichnis. Eine veraltete Token-Zeile in dieser Datei würde nur greifen, wenn die Variable nicht über die Umgebung gesetzt ist (z. B. `EBAY_USER_ACCESS_TOKEN`, `EBAY_APP_ACCESS_TOKEN`; beide setzen wir nicht).
- Schlägt das Schreiben fehl, ist das nicht fatal: der Code loggt `could not be persisted` und arbeitet mit dem Token im Speicher weiter (`oauth.js`, `isCredentialPersistenceError`).
- Die Datei liegt unter `node_modules/` und ist durch `.gitignore` (`node_modules/`, `.env`) vor einem Commit geschützt. Sie ist aber ein Klartext-Token außerhalb des Secret-Managers. Access-Tokens leben 2 Stunden, App-Token ebenfalls; der Refresh-Token selbst wird nach Stand der Analyse nicht geschrieben.

**Gegenmaßnahme (umgesetzt und getestet, siehe Auflagen #1):** `ln -sf /dev/null node_modules/ebay-mcp/.env`, per `postinstall` nach jedem `npm install`. Lesen und Schreiben laufen ins Leere, nichts bleibt auf Platte.

### Weitere Schreibzugriffe
- Logs: `utils/logger.js` legt `~/.ebay-mcp/logs/` an. Dateilogs (`error.log`, `combined.log`, `debug.log`) nur bei `EBAY_ENABLE_FILE_LOGGING=true`, Standard aus. Konsole geht nach stderr.
- `grep -rnE "writeFile|appendFile|writeSync|createWriteStream" build` trifft: Setup-Skripte, `credentialSession.js`, Logger. Sonst nichts.

## 3. `child_process`, `eval`, `new Function`

| Fundstelle | Kontext | Laufzeitpfad? |
|---|---|---|
| `scripts/setupWizard.js` (`spawn`) | startet Client-/Setup-Befehle | nein, nur Setup |
| `scripts/devSync.js` (`execSync npx openapi-typescript`) | Entwicklerwerkzeug zur Typgenerierung | nein |
| `scripts/securityChecker.js` (`execSync git ls-files .env`) | Check, ob `.env` eingecheckt ist | nein |

`eval(` und `new Function` kommen im Build nicht vor (die Treffer `.exec(` sind RegExp-Aufrufe). Kein `child_process` im Server-Pfad (`index.js`, `mcp/`, `tools/`, `api/`, `auth/`).

## 4. `npm audit --omit=dev`

```
found 0 vulnerabilities
```

Produktionsabhängigkeiten (181 Pakete im `node_modules`): `@modelcontextprotocol/sdk` 1.29.0, `@modelcontextprotocol/ext-apps` 1.7.4, `express`, `helmet`, `cors` (nur HTTP-Transport, ungenutzt), `dotenv`, `dotenv-stringify`, `effect`, `jose`, `prompts`, `update-notifier`, `winston`, `zod`, `fast-xml-parser`. Der Lockfile pinnt alle transitiven Versionen.

## 5. OAuth-Scopes

Quelle: `docs/auth/production_scopes.json`, geladen von `config/environment.js` (`getDefaultScopes('production')`). Standardmäßig fordert der Consent-Link **alle 26 Einträge** an (Präfix `https://api.ebay.com/oauth/api_scope`):

`<Wurzel>`, `/commerce.feedback`, `/commerce.feedback.readonly`, `/commerce.identity.readonly`, `/commerce.message`, `/commerce.notification.subscription`, `/commerce.notification.subscription.readonly`, `/commerce.shipping`, `/commerce.vero`, `/sell.account`, `/sell.account.readonly`, `/sell.analytics.readonly`, `/sell.finances`, `/sell.fulfillment`, `/sell.fulfillment.readonly`, `/sell.inventory`, `/sell.inventory.mapping`, `/sell.inventory.readonly`, `/sell.marketing`, `/sell.marketing.readonly`, `/sell.payment.dispute`, `/sell.reputation`, `/sell.reputation.readonly`, `/sell.stores`, `/sell.stores.readonly`, sowie `https://api.ebay.com/oauth/scope/sell.edelivery`.

Abdeckung für den Skill:
- `sell.inventory` (Inventory Item, Offer, Location, Publish): ja.
- `sell.account` (Policies, Opt-in, Privileges): ja.
- Taxonomy, Metadata, Browse: Application-Token mit Wurzel-Scope `https://api.ebay.com/oauth/api_scope` reicht; der Server nutzt Client-Credentials mit genau diesem Scope (`getOrRefreshAppAccessToken`).
- `commerce.media`: **kommt in keiner Scope-Datei vor.** Ein Scope dieses Namens existiert im Paket nicht. Der Bildupload (`ebay_upload_images`, Media API `/commerce/media/v1_beta`, `createImageFromFile`) nutzt im Code keinen eigenen Scope. Nach eBay-Dokumentation zur Media API genügt `sell.inventory`; das konnte hier ohne Live-Aufruf nicht bestätigt werden. Erst ein Live-Test zeigt es (siehe Auflagen #3).

Auflage: Die Standardliste ist deutlich breiter als nötig (u. a. `sell.finances`, `commerce.message`, `sell.payment.dispute`, `sell.marketing`, `sell.stores`, `commerce.vero`). Das Paket liest `EBAY_OAUTH_SCOPES` (Leerzeichen- oder Komma-getrennt, nur URIs `https://api.ebay.com/oauth/...`). Für Least Privilege diese Variable setzen auf:
`https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/sell.account`
Die Variable wirkt nur beim Bau der Consent-URL durch den Server/Setup; wenn der Token anderweitig beschafft wird, muss dort dieselbe Liste verwendet werden.

## 6. Umgebungsvariablen, die der Server liest

Bestätigt (Runtime, `config/environment.js`, `config/toolFamilies.js`, `config/mediaAccess.js`):

| Variable | Bedeutung |
|---|---|
| `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | Pflicht |
| `EBAY_REDIRECT_URI` | RuName, nur für Consent-URL und Code-Exchange |
| `EBAY_ENVIRONMENT` | `production`, sonst Sandbox (Default Sandbox!) |
| `EBAY_MARKETPLACE_ID` | Default `EBAY_US` |
| `EBAY_CONTENT_LANGUAGE` | Default `en-US` |
| `EBAY_USER_REFRESH_TOKEN` | Refresh-Token |
| `EBAY_MCP_TOOLS` | `all`, `dynamic` oder Familienliste; Tippfehler bricht den Start ab |
| `EBAY_MCP_MEDIA_DIRS` | erlaubte Verzeichnisse für Bild-/Videodateien (`path.delimiter`-getrennt, absolute Pfade) |
| `EBAY_MCP_UI` | `off` schaltet MCP-Apps-UI ab |

Zusätzlich gelesen: `EBAY_USER_ACCESS_TOKEN`, `EBAY_APP_ACCESS_TOKEN` (siehe Abschnitt 2), `EBAY_OAUTH_SCOPES`, `EBAY_READ_ONLY` (filtert Schreib-Tools heraus; für unseren Zweck unbrauchbar, da wir schreiben), `EBAY_MCP_MEDIA_ROOT`, `EBAY_SITE_ID`, `EBAY_LOG_LEVEL`, `EBAY_ENABLE_FILE_LOGGING`, `EBAY_OAUTH_CALLBACK_PORT`, `EBAY_MCP_API_BASE_URL`, `EBAY_MCP_DISABLE_AUTH_HEADER`, `NO_UPDATE_NOTIFIER` (über update-notifier). Nur HTTP-Transport (`serverHttp.js`, ungenutzt): `MCP_PORT`, `MCP_HOST`, `MCP_AUTH_TOKEN`, `OAUTH_*`, `PORT`.

`.env`-Verhalten: gelesen wird nur `node_modules/ebay-mcp/.env`, nicht die `.env` des Arbeitsverzeichnisses (siehe Abschnitt 2). Eine `.env` im Projektwurzelverzeichnis hat keine Wirkung.

`EBAY_MCP_TOOLS=inventory,taxonomy,metadata,account,browse` setzt das Setup (siehe README, Abschnitt Secrets). Ohne den Eintrag wären alle 384 Tools aktiv (inkl. Löschen von Bestellungen, Marketing, Finanzen). Die fünf Familien sind gültige Schlüssel (`TOOL_FAMILY_KEYS`). Das Bild-Tool `ebay_upload_images` gehört zur Familie `inventory`.

## 7. MCP-Toolnamen

Präfix in Claude Code: `mcp__ebay__`. Alle Namen im Build bestätigt (`tools/categories/*.js`). Die Familie steht in der letzten Spalte.

| eBay-Operation | MCP-Tool | Familie |
|---|---|---|
| Standard-Kategoriebaum-ID | `mcp__ebay__ebay_get_default_category_tree_id` | taxonomy |
| Kategorievorschläge | `mcp__ebay__ebay_get_category_suggestions` | taxonomy |
| Item Aspects je Kategorie | `mcp__ebay__ebay_get_item_aspects_for_category` | taxonomy |
| Item Aspects aller Blätter (Riesen-Download, nicht nutzen) | `mcp__ebay__ebay_fetch_item_aspects` | taxonomy |
| Zustandsrichtlinien | `mcp__ebay__ebay_get_item_condition_policies` | metadata |
| Versandservices | `mcp__ebay__ebay_get_shipping_services` | metadata |
| Listing-Struktur-Policies | `mcp__ebay__ebay_get_listing_structure_policies` | metadata |
| Rückgabe-Metadaten | `mcp__ebay__ebay_get_return_policy_metadata` | metadata |
| Privilegien (Read-only-Kontocheck) | `mcp__ebay__ebay_get_privileges` | account |
| Opt-in in Programm (Business Policies) | `mcp__ebay__ebay_opt_in_to_program` | account |
| Opted-in-Programme lesen | `mcp__ebay__ebay_get_opted_in_programs` | account |
| Rückgabe-Policy anlegen | `mcp__ebay__ebay_create_return_policy` | account |
| Rückgabe-Policies lesen | `mcp__ebay__ebay_get_return_policies` | account |
| Rückgabe-Policy einzeln lesen | `mcp__ebay__ebay_get_return_policy` | account |
| Zahlungs-Policy anlegen | `mcp__ebay__ebay_create_payment_policy` | account |
| Zahlungs-Policies lesen | `mcp__ebay__ebay_get_payment_policies` | account |
| Zahlungs-Policy einzeln lesen | `mcp__ebay__ebay_get_payment_policy` | account |
| Versand-Policy (Fulfillment) anlegen | `mcp__ebay__ebay_create_fulfillment_policy` | account |
| Versand-Policies lesen | `mcp__ebay__ebay_get_fulfillment_policies` | account |
| Versand-Policy einzeln lesen | `mcp__ebay__ebay_get_fulfillment_policy` | account |
| Lagerort anlegen | `mcp__ebay__ebay_create_inventory_location` | inventory |
| Lagerorte lesen | `mcp__ebay__ebay_get_inventory_locations` | inventory |
| Bilder hochladen (lokale Dateien, EPS-URLs zurück) | `mcp__ebay__ebay_upload_images` | inventory |
| Inventory Item anlegen/ersetzen | `mcp__ebay__ebay_create_or_replace_inventory_item` | inventory |
| Inventory Item lesen | `mcp__ebay__ebay_get_inventory_item` | inventory |
| Offer anlegen | `mcp__ebay__ebay_create_offer` | inventory |
| Offer lesen | `mcp__ebay__ebay_get_offer` | inventory |
| Offers je SKU lesen | `mcp__ebay__ebay_get_offers` | inventory |
| Offer ändern | `mcp__ebay__ebay_update_offer` | inventory |
| Offer veröffentlichen | `mcp__ebay__ebay_publish_offer` | inventory |
| Offer zurückziehen | `mcp__ebay__ebay_withdraw_offer` | inventory |
| Browse-Suche (Preisvergleich) | im Python-Modul `pricing/` direkt per REST, nicht über MCP | – |

Hinweis: Eine Familie `media` gibt es nicht; das Bild-Tool hängt an `inventory`. `ebay_get_item_condition_policies` und `ebay_get_shipping_services` haben unterschiedliche Parameter (Marktplatz-ID); Details stehen in den Tool-Schemas des laufenden Servers (`/mcp`).

## Auflagen

Maßnahmen zu den Befunden aus Abschnitt 2 und 5:

1. **Token-Persistenz auf `/dev/null` umgeleitet.** `package.json` enthält `"scripts": { "postinstall": "ln -sf /dev/null node_modules/ebay-mcp/.env" }`. Der Server schreibt per `writeFileSync` durch den Symlink ins Leere und liest per `readFileSync` eine leere Datei. Access- und App-Tokens landen damit nicht auf Platte; die echten Werte kommen ausschließlich aus der Umgebung. Prüfen: `ls -la node_modules/ebay-mcp/` zeigt `.env -> /dev/null`. Das Skript läuft nach jedem `npm install` bzw. `npm ci` automatisch.
2. **Scopes begrenzt (Least Privilege).** `EBAY_OAUTH_SCOPES=https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/sell.account`. Die Variable begrenzt nur die Consent-URL. Refresh-Requests senden keinen Scope; die Rechte des Tokens sind das, was beim Consent gewährt wurde. Das mitgelieferte Skript `scripts/ebay_oauth.py` baut die Consent-URL mit genau diesen drei Scopes. Nach dem OAuth-Lauf prüfen, dass nur diese drei gewährt wurden.
3. **Bildupload (Media API):** Er lief im Praxistest mit `sell.inventory`, ein zusätzlicher Scope war nicht nötig.
4. **Tool-Familien begrenzen:** `EBAY_MCP_TOOLS=inventory,taxonomy,metadata,account,browse` und `EBAY_ENVIRONMENT=production` setzen.
