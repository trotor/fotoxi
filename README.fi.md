# Fotoxi

> **foto** (valokuva) + **ξ** (ksi, kreikan kirjain — tuntematon, löydettävä)

Paikallinen valokuvien ja videoiden hallintatyökalu. Indeksoi median OneDrivestä, Google Drivestä, iCloud Drivestä ja paikallisista kansioista. Luo haettavan metatietokannan EXIF-tiedoilla, visuaalisilla sormenjäljillä ja valinnaisilla tekoälykuvauksilla. Tunnistaa ja auttaa hallitsemaan duplikaatteja.

[English README](README.md)

## Mihin Fotoxi sopii?

**Ongelma:** Sinulla on tuhansia valokuvia ja videoita hajallaan eri pilvipalveluissa, puhelimen varmuuskopioissa ja paikallisissa kansioissa. Monet ovat duplikaatteja, osa on sumeita, etkä löydä mitään.

**Tyypillinen työnkulku:**

1. **Osoita Fotoxi kuvakansioihisi** — OneDrive, Google Drive, paikalliset kansiot. Yksi klikkaus per lähde.
2. **Anna indeksoida** — Fotoxi skannaa kaikki kansiot rekursiivisesti, poimii EXIF-metatiedot (päivämäärä, kamera, GPS, asetukset), luo pikkukuvat ja laskee visuaaliset sormenjäljet. Pilvivedostot ladataan väliaikaisesti ja vapautetaan käsittelyn jälkeen.
3. **Selaa ja hae** — Suodata päivämäärän, kameran, kansion tai mediatyypin mukaan. Järjestä päivämäärän, nimen, koon tai visuaalisen samankaltaisuuden mukaan. Loputon vieritys koko kokoelmaan.
4. **Siivoa duplikaatit** — Fotoxi löytää visuaalisesti samankaltaiset kuvat ja sarjakuvaukset. Yksi klikkaus "säilytä suositeltu" ratkaisee useimmat ryhmät välittömästi. Voit myös suodattaa kansion mukaan ja säilyttää alkuperäiset haluamastasi sijainnista.
5. **Hylkää tarpeettomat** — Merkitse kuvia poistettaviksi suoraan hakuruudukosta. Tarkista hylätyt ennen lopullista poistoa.
6. **Valinnaisesti: tekoälykuvaukset** — Yhdistä paikallinen Ollama-näkömalli (LLaVA, Moondream) tuottamaan automaattisesti kuvaukset ja tagit kokotekstihakua varten.

**Parhaimmillaan:**
- Kuvakirjastojen yhdistäminen useista pilvipalveluista ja laitteista
- Duplikaattien löytäminen ja poistaminen puhelimen varmuuskopioista
- Vuosien aikana kertyneiden kuvakaappausten, WhatsApp-kuvien ja sarjakuvausten siivoaminen
- Haettavan indeksin rakentaminen suurelle kuvakokoelmalle
- Median hallinta ilman tietojen lähettämistä kolmansille osapuolille

## Ominaisuudet

- **Monikansio-indeksointi** — OneDrive, Google Drive, iCloud Drive, paikalliset kansiot
- **Kuvat ja videot** — JPEG, PNG, HEIC, RAW, MP4, MOV, AVI, MKV ja muut
- **EXIF-metatiedot** — Päivämäärä, kamera, GPS, aukko, ISO, valotusaika, polttoväli
- **Duplikaattitunnistus** — Visuaalinen sormenjälki (pHash) + sarjakuvaustunnistus
- **Duplikaattien hallinta** — Ruudukkovertailu "säilytä suositeltu" -pikavalinnalla
- **Tekoälykuvaukset** — Valinnainen paikallinen Ollama-näkömalli (LLaVA, Moondream)
- **Kokotekstihaku** — SQLite FTS5 kuvauksista, tageista ja tiedostonimistä
- **Kansioselaus** — Puumainen kansionavigaatio breadcrumb-polulla ja kuvalukumäärillä
- **Mediatyyppisuodatin** — Vaihda kaikki/kuvat/videot välillä
- **Pilvioptiomointi** — macOS Files On-Demand, automaattinen lataus ja vapautus
- **Web-käyttöliittymä** — React SPA, tumma teema, loputon vieritys, zoomaus-hover, tilamerkit
- **Komentorivi** — Kaikki toiminnot CLI:n kautta
- **Hylkää/palauta** — Merkitse kuvia poistettaviksi hakuruudukosta, tarkista ennen poistoa
- **Kansion piilotus** — Piilota kokonaisia kansioita indeksoinnista yhdellä klikkauksella
- **Tietokantamigraatiot** — Alembic skeemamuutoksiin
- **EXIF-orientaatio** — Pikkukuvat käännetään automaattisesti oikein

## Pikaopas

```bash
# Kloonaa ja asenna
git clone https://github.com/trotor/fotoxi.git
cd fotoxi
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Rakenna käyttöliittymä
cd frontend && npm install && npm run build && cd ..

# Käynnistä
python fotoxi.py
# Avaa http://localhost:8000
```

## Komentorivi

```bash
python fotoxi.py                    # Käynnistä web-käyttöliittymä (oletus)
python fotoxi.py serve -p 3000      # Mukautettu portti
python fotoxi.py add <kansio>       # Lisää lähdekansio
python fotoxi.py folders            # Listaa lähdekansiot
python fotoxi.py remove <kansio>    # Poista lähdekansio
python fotoxi.py scan               # Skannaa uudet/muuttuneet tiedostot
python fotoxi.py index              # Aja koko indeksointi
python fotoxi.py status             # Tietokannan tilanne
python fotoxi.py duplicates         # Näytä duplikaattiryhmät
python fotoxi.py backup             # Luo aikaleimattu varmuuskopio
python fotoxi.py migrate            # Aja tietokantamigraatiot
python fotoxi.py rebuild-thumbs     # Luo pikkukuvat uudelleen (korjaa orientaatio)
```

## Miten toimii

### Indeksointiputki

1. **Skannaus** — Löytää kuva- ja videotiedostot rekursiivisesti
2. **Metadata** — EXIF-tiedot, visuaaliset sormenjäljet (pHash/dHash), pikkukuvat (300px)
3. **Tekoälyanalyysi** — Valinnainen: Ollama-näkömalli tuottaa kuvaukset, tagit ja laatuarviot
4. **Duplikaattiryhmittely** — pHash-samankaltaisuus (Hamming < 10) + sarjakuvaustunnistus (sama kamera, < 5s). Union-Find yhdistää päällekkäiset.

### Pilvi-integraatio (macOS)

- Pilvivedostot `~/Library/CloudStorage/` -kansiossa luetaan normaaleina polkuina
- macOS lataa tiedostot automaattisesti käsiteltäessä
- Käsittelyn jälkeen `brctl evict` vapauttaa paikallisen kopion
- Toimii OneDriven, Google Driven ja iCloud Driven kanssa — ei API-avaimia tarvita

### Apple Photos Library

- **originals/** — oikeat valokuvat, mukana indeksoinnissa
- **derivatives/**, **masters/**, **resources/** — Applen luomia kopioita, ohitetaan automaattisesti
- Photos Libraryn sisäiset duplikaatit eivät näy duplikaattinäkymässä

### Tietojen tallennus

- **SQLite** kansiossa `data/fotoxi.db`, FTS5-kokotekstihaku
- **Pikkukuvat** kansiossa `data/thumbs/` (300px JPEG)
- **Asetukset** tallennetaan kantaan (lähdekansiot, mallin asetukset, piilotuslistat)

## Asetukset

| Asetus | Oletus | Kuvaus |
|--------|--------|--------|
| `ollama_model` | `llava:7b` | Näkömalli tekoälykuvauksiin |
| `ai_language` | `english` | Tekoälykuvausten kieli |
| `ai_quality_enabled` | `true` | Laatupisteytys (0-1) |
| `phash_threshold` | `10` | Duplikaattien Hamming-etäisyys (pienempi = tiukempi) |
| `exclude_patterns` | derivatives, masters, ... | Ohitettavat kansioiden nimet |

## Teknologiapino

| Kerros | Teknologia |
|--------|-----------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Tietokanta | SQLite + FTS5, SQLAlchemy, aiosqlite, Alembic |
| Kuva-analyysi | Ollama, exifread, imagehash, Pillow, pillow-heif, OpenCV |
| Frontend | React 18, Vite, TypeScript, Tailwind CSS |
| Tilanhallinta | TanStack Query (React Query) |

## Vaatimukset

- Python 3.11+
- Node.js 18+
- macOS (pilvi-integraatioon; perustoiminnot toimivat Linuxilla ilman `brctl`:tä)
- Ollama (valinnainen, tekoälykuvauksiin)

## Lisenssi

MIT
