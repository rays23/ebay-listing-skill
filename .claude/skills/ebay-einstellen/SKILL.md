---
name: ebay-einstellen
description: Erstellt aus einem oder mehreren Fotos ein eBay.de-Festpreisangebot (Preisvorschlag erlaubt) und veröffentlicht es nach einem Ja. Nutzen, wenn der Nutzer einen Artikel per Foto bei eBay einstellen will.
argument-hint: <foto> [weitere fotos]
---

# eBay-Angebot aus Foto

Die Skill läuft im Repo-Root. Defaults: `config/listing-defaults.json`. Beschreibungsvorlage: `.claude/skills/ebay-einstellen/beschreibung-vorlage.md`.

Fehlt `config/listing-defaults.json`: stoppen und auf den Abschnitt „Einrichtung“ im README verweisen (Vorlage: `config/listing-defaults.example.json`).

Regeln für die Vorlage:
- `FLIESSTEXT` umfasst 2 bis 4 Sätze, beschreibt sichtbare Mängel ehrlich und erfindet nichts.
- `MERKMALE_ALS_LI` enthält höchstens 6 `<li>` mit den wichtigsten Merkmalen.

## Ablauf

1. **Fotos prüfen.** Jeder Pfad aus den Argumenten muss existieren. Sonst nennen und stoppen. Alle Fotos mit Read ansehen.
2. **Erkennen.** Bestimme Produktart, Marke, Modell oder Variante, Farbe, Zustand, Größenklasse (bei Warenwert ab `insuredShippingFromEur` siehe Schritt 7; S: DHL Päckchen S bis 2 kg und 35 × 25 × 10 cm, M: DHL Päckchen M bis 2 kg und 60 × 30 × 15 cm, L: DHL Paket bis 5 kg, XL: DHL Paket bis 10 kg, XXL: DHL Paket bis 20 kg, XXXL: DHL Paket bis 31,5 kg; maßgeblich sind Gewicht und Maße mit Verpackung), einen Suchbegriff (Marke + Modell, ohne Füllwörter) und einen Sicherheitswert.
   - Ist die Sicherheit niedrig: **genau eine** gezielte Rückfrage, zum Beispiel „Ist das die XM4 oder die XM5?“.
   - Wiegt der Artikel mit Verpackung über 31,5 kg oder ist er Sperrgut über 120 × 60 × 60 cm: stoppen und dem Nutzer sagen, dass Abholung nicht im Umfang ist.
   - Gewicht und Verpackungsmaße bei Geräten im Web nachschlagen (Herstellerangabe, Verpackungsgewicht), nicht schätzen.
3. **Kategorie.**
   - `mcp__ebay__ebay_get_default_category_tree_id` für `EBAY_DE`, dann `mcp__ebay__ebay_get_category_suggestions` mit dem Suchbegriff. Die passendste Blattkategorie nehmen.
   - `mcp__ebay__ebay_get_item_aspects_for_category`: Alle Pflichtmerkmale füllen. Die Antwort ist oft über 100 KB groß und landet als Datei: dann per `jq -r '.aspects[] | [.localizedAspectName, .aspectConstraint.aspectRequired, .aspectConstraint.aspectUsage] | @tsv'` auswerten, die erlaubten Werte je Pflichtmerkmal gezielt mit `jq -r '.aspects[] | select(.localizedAspectName=="<name>") | .aspectValues[]?.localizedValue'` holen. Nicht Erkennbares mit dem erlaubten Wert für unbekannt bzw. nicht zutreffend belegen, sonst die plausibelste erlaubte Option. Niemals `mcp__ebay__ebay_fetch_item_aspects` verwenden (Riesen-Download).
   - Gültige Zustände für die Kategorie über `mcp__ebay__ebay_get_item_condition_policies` mit `marketplaceId: EBAY_DE` und `filter: categoryIds:{<id>}` holen und den passenden Zustand wählen. Im Inventory Item steht der Enum-Wert, z. B. `USED_EXCELLENT` für „Gebraucht“ (3000).
4. **Neupreis.** Den Suchbegriff URL-kodiert einsetzen und `firecrawl scrape "https://www.idealo.de/preisvergleich/MainSearchProductCategory.html?q=<suchbegriff>" --format markdown --only-main-content` ausführen. Den Treffer mit **demselben Modell** suchen, kein Zubehör und kein Nachfolger, und dessen „ab“-Preis nehmen. Ist kein Treffer eindeutig, den Neupreis weglassen.
5. **Preis.** `uv run python -m pricing --query "<suchbegriff>" --category-id <id> --condition <used|new> [--new-price <x>] [--exclude <wort>]...`
   - `--exclude` (mehrfach erlaubt) mit bekannten Geschwistervarianten setzen, die nicht im Suchbegriff stehen, z. B. Nano, Plus, Pro, Mini, Max, 2230, 2242, Vorgänger- oder Nachfolgerbezeichnung. Die Suche filtert Titel: Alle Wörter des Suchbegriffs müssen im Titel stehen, Exclude-Wörter dürfen nicht als ganzes Wort vorkommen.
   - Restrisiken: Steht ein Exclude-Wort in einer Verneinung („ohne Plus“), fällt ein echtes Vergleichsangebot raus. Suchwörter treffen auch als Teilstring („1tb“ trifft „21TB“, „a7“ trifft „A7C“), deshalb Varianten mit `--exclude` ausschließen. Exclude-Wörter ohne Umlaute oder ß angeben.
   - Ausgabe ist JSON mit den Feldern `query`, `category_id`, `candidate_count`, `active_count`, `active_median`, `new_price`, `cap_applied`, `listing_price`, `auto_accept_price`, `warnings`.
   - Exit 0: ok. Exit 2 (`NO_COMPS`): genau **einmal** lockern (Versions- und Füllangaben streichen, Marke + Modell + Kapazität/Größe behalten, `--exclude` beibehalten). Bei erneutem Exit 2 den Nutzer nach einem Preis fragen, nicht raten. Kam der Preis aus der gelockerten Suche, die Zeile `Warnungen:` um „Preis aus gelockerter Suche“ ergänzen.
   - Exit 1: Fehlermeldung zeigen und stoppen.
6. **Titel.** Höchstens 80 Zeichen, Muster: Marke Modell Variante Farbe + Kernmerkmal. Keine Großbuchstaben-Wörter, kein „TOP“ und kein „!!!“. Bei mehr als 80 Zeichen von hinten kürzen.
7. **Vorschau** genau in diesem Format, ohne Em-Dash:

       Titel:      <titel>
       Zustand:    <zustand> – <ein Satz zu sichtbaren Mängeln>
       Kategorie:  <pfad>
       Preis:      <listing_price> € (Preisvorschlag, Auto-Annahme ab <auto_accept_price> €)
       Basis:      "<query>" · <active_count> passende von <candidate_count> Angeboten · Median <active_median> € · Neupreis <x € | unbekannt> (Deckel: ja/nein)
       Versand:    <fulfillmentPolicyNames[Größe]> (<Größe>[, statt <S|M> wegen Warenwert])
       Warnungen:  <warnings, sonst Zeile weglassen>
       Einstellen? (ja / nein / Korrektur, z. B. "Preis 40")

   - Versicherter Versand: Liegt `listing_price` ≥ `insuredShippingFromEur` (aus `config/listing-defaults.json`) und ist die Klasse aus Schritt 2 S oder M (DHL Päckchen, ohne Haftung), wird L (Paket, versichert) gewählt und in der Vorschau als `(L, statt S wegen Warenwert)` bzw. `(L, statt M wegen Warenwert)` gezeigt. Diese Bewertung gilt bei **jeder** neuen Vorschau neu, auch nach einer Preiskorrektur: Korrektur auf ≥ Schwelle hebt S/M auf L, Korrektur darunter setzt die ursprüngliche Klasse aus Schritt 2 zurück.
   - Seriennummer: Ist auf einem Foto eine Seriennummer lesbar, die Zeile `Warnungen:` um „Seriennummer auf Foto <n> lesbar“ ergänzen. Die Entscheidung bleibt beim Nutzer.
   - Bei einer Korrektur: Wert übernehmen. Preisänderungen setzen `auto_accept_price = round(neuer Preis × 0,85)`. Danach Versandklasse neu bewerten (siehe oben) und die Vorschau neu zeigen.
   - Bei „nein“: ohne Schreibzugriff abbrechen.
8. **Veröffentlichen** (nur nach „ja“):
   1. SKU einmal pro Lauf erzeugen: `EL-<YYYYMMDD>-<6 Zeichen aus sha1 des ersten Fotopfads>`. Bei einem Neuversuch dieselbe SKU verwenden.
   2. Fotos nach `staging/` kopieren und mit `mcp__ebay__ebay_upload_images` hochladen.
      - Scheitert eine `.heic`-Datei: `sips -s format jpeg <src> --out staging/<name>.jpg` und erneut hochladen.
   3. `mcp__ebay__ebay_create_or_replace_inventory_item`:
      - SKU, `availability.shipToLocationAvailability.quantity = 1`
      - Zustand
      - `product`: `title`, `description` (Vorlage gefüllt), `aspects`, `imageUrls`
   4. Vor dem Anlegen mit `mcp__ebay__ebay_get_offers` (SKU) prüfen, ob es schon ein Offer gibt. Wenn ja, dieses per `mcp__ebay__ebay_update_offer` aktualisieren statt ein neues anzulegen. Sonst `mcp__ebay__ebay_create_offer` mit:
      - `marketplaceId`, `format: FIXED_PRICE`, `listingDuration: GTC`, `availableQuantity: 1`, `categoryId`
      - `merchantLocationKey`
      - `listingPolicies` mit `paymentPolicyId`, `returnPolicyId`, `fulfillmentPolicyId` nach Größe, und `bestOfferTerms: {bestOfferEnabled: true, autoAcceptPrice: {value, currency: EUR}}`
      - `pricingSummary.price: {value, currency: EUR}`
   5. `mcp__ebay__ebay_publish_offer`. Enthält die Antwort keine `listingId`, `mcp__ebay__ebay_get_offer` (offerId) lesen und `listing.listingId` nehmen. Bei einem Fehler zu einem fehlenden Merkmal: ergänzen, Inventory Item aktualisieren, **einmal** neu veröffentlichen. Danach den Fehler melden. Das Item bleibt als Entwurf stehen.
   6. Die Dateien in `staging/` löschen, die zu diesem Lauf gehören.
9. **Ergebnis:** `Live: https://www.ebay.de/itm/<listingId>`

## Regeln

- Niemals ohne ausdrückliches „ja“ in derselben Vorschau-Runde veröffentlichen.
- Keine Secrets ausgeben. Werte aus der Umgebung (`EBAY_CLIENT_SECRET`, `EBAY_USER_REFRESH_TOKEN`) nie anzeigen.
- Vor dem ersten schreibenden `mcp__ebay__*`-Aufruf eines Laufs `test -L node_modules/ebay-mcp/.env` prüfen. Ist es kein Symlink, zuerst `npm run postinstall` ausführen. So landen keine Tokens auf der Platte (siehe `docs/ebay-mcp-review.md`, Auflagen #1).
- Antwortet ein `mcp__ebay__*`-Tool mit 401 oder `invalid_grant`, ist der Nutzertoken abgelaufen oder widerrufen. Stoppen und auf das README verweisen (Abschnitt „OAuth-Token holen“, danach den neuen Refresh-Token in den Secret-Manager schreiben und Claude Code neu starten).
- Die Beschreibung erfindet nichts: kein Zubehör, keine OVP und keine Funktionsprüfung, die weder auf dem Foto zu sehen noch vom Nutzer bestätigt sind.
