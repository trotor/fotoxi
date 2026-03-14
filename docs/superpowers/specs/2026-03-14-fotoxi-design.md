# Fotoxi - Valokuvien hallinta- ja metatietokantasovellus

## Yleiskuvaus

Fotoxi on paikallinen sovellus joka indeksoi valokuvia OneDrivesta, Google Drivestä ja paikallisista kansioista, luo niistä haettavan metatietokannan AI-kuvauksilla ja EXIF-tiedoilla, sekä auttaa tunnistamaan ja karsimaan duplikaatit.

## Suunnittelupäätökset

- **Arkkitehtuuri:** Yksi Python-prosessi (FastAPI) + React SPA. Ei erillistä jonopalvelua – indeksointi taustasäikeessä.
- **Pilvitiedostot:** macOS Files On-Demand (File Provider) – tiedostot luetaan normaaleina polkuina, macOS lataa automaattisesti. Käsittelyn jälkeen `brctl evict` vapauttaa paikallisen kopion.
- **Tietokanta:** SQLite + FTS5 tekstihakuun. Vektorihaku (sqlite-vss tai erillinen vektoritietokanta) lisätään myöhemmin.
- **AI-malli:** Ollama, oletuksena LLaVA 7B, konfiguroitavissa asetuksista. Tuottaa kuvauksen, tagit ja valinnaisen laatuarvion.
- **Duplikaattitunnistus:** EXIF-aikaleima + laite + perceptual hash (pHash/dHash). Ryhmittelee sarjakuvaukset ja lähes identtiset kuvat.
- **Duplikaattien hallinta:** Rinnakkaisvertailu-UI, kaksi kuvaa vierekkäin EXIF-tiedoilla ja AI-suosituksella.
- **Haku:** FTS5-tekstihaku kuvauksista, tageista ja tiedostonimistä + suodattimet (päivämäärä, kamera, sijainti, laatu).
- **AI-laatuarvio:** Kytkettävissä pois asetuksista.
- **AI-kuvausten kieli:** Englanti oletuksena (LLaVA tuottaa laadukkaampia kuvauksia englanniksi). Konfiguroitavissa asetuksista.
- **Hylätyt kuvat:** Hylkäys piilottaa kuvan hakutuloksista mutta ei poista tiedostoa levyltä. Erillinen "poista hylätyt pysyvästi" -toiminto asetuksissa.
- **Palvelin:** Sidotaan `127.0.0.1`:iin (vain localhost). Ei autentikaatiota v1:ssä.

## Projektirakenne

```
fotoxi/
├── backend/
│   ├── main.py              # FastAPI-sovellus, yksi prosessi
│   ├── indexer/
│   │   ├── scanner.py       # Tiedostojärjestelmän skannaus
│   │   ├── exif.py          # EXIF-metatietojen luku
│   │   ├── hasher.py        # pHash/dHash-sormenjäljet
│   │   ├── analyzer.py      # Ollama-integraatio
│   │   └── eviction.py      # brctl evict -pilvioptiomointi
│   ├── db/
│   │   ├── models.py        # SQLite-skeema (SQLAlchemy/aiosqlite)
│   │   └── queries.py       # Hakukyselyt ja suodattimet
│   ├── grouping/
│   │   └── duplicates.py    # Duplikaattiryhmien muodostus
│   ├── api/
│   │   ├── routes.py        # REST-endpointit
│   │   └── websocket.py     # Indeksoinnin edistyminen reaaliajassa
│   └── config.py            # Asetukset
├── frontend/                # React SPA (Vite + TypeScript)
│   └── src/
│       ├── pages/
│       │   ├── Search.tsx       # Haku + suodattimet
│       │   ├── Duplicates.tsx   # Rinnakkaisvertailu-näkymä
│       │   └── Settings.tsx     # Asetukset
│       └── components/
│           ├── ImageCompare.tsx  # Kahden kuvan rinnakkaisvertailu
│           ├── FilterBar.tsx     # Suodatinpalkki
│           └── ProgressBar.tsx   # Indeksoinnin edistyminen
└── fotoxi.py                # Käynnistää kaiken yhdellä komennolla
```

## Tietomalli (SQLite)

### images

| Kenttä | Tyyppi | Kuvaus |
|--------|--------|--------|
| id | INTEGER PK | |
| file_path | TEXT UNIQUE | Alkuperäinen polku |
| file_name | TEXT | Tiedostonimi |
| file_size | INTEGER | Tavuina |
| phash | TEXT | Perceptual hash (hex) |
| dhash | TEXT | Difference hash (hex) |
| width | INTEGER | |
| height | INTEGER | |
| format | TEXT | JPEG, PNG, HEIC... |
| exif_date | DATETIME | Kuvauspäivä |
| exif_camera_make | TEXT | Esim. "Apple" |
| exif_camera_model | TEXT | Esim. "iPhone 14 Pro" |
| exif_gps_lat | REAL | GPS-leveysaste |
| exif_gps_lon | REAL | GPS-pituusaste |
| exif_focal_length | REAL | |
| exif_aperture | REAL | |
| exif_iso | INTEGER | |
| exif_exposure | TEXT | |
| ai_description | TEXT | Ollama-mallin tuottama kuvaus |
| ai_tags | TEXT | JSON-lista, esim. ["maisema", "järvi"] |
| ai_quality_score | REAL | 0.0–1.0, kytkettävissä pois |
| ai_model | TEXT | Mikä malli tuotti kuvauksen |
| status | TEXT | "pending", "indexed", "kept", "rejected", "error", "missing" |
| error_message | TEXT | Virheilmoitus jos status="error" |
| indexed_at | DATETIME | |
| created_at | DATETIME | Rivin luontiaika |
| updated_at | DATETIME | Viimeisin päivitys |
| file_mtime | REAL | Tiedoston muokkausaika (os.path.getmtime) |
| source_type | TEXT | "local", "onedrive", "gdrive" |

### duplicate_groups

| Kenttä | Tyyppi | Kuvaus |
|--------|--------|--------|
| id | INTEGER PK | |
| created_at | DATETIME | |
| match_type | TEXT | "phash", "burst", "phash+burst" |

### duplicate_group_members

| Kenttä | Tyyppi | Kuvaus |
|--------|--------|--------|
| group_id | INTEGER FK | |
| image_id | INTEGER FK | |
| is_best | BOOLEAN | AI:n suosittelema |
| user_choice | TEXT | "keep", "reject", NULL |

### settings

| Kenttä | Tyyppi | Kuvaus |
|--------|--------|--------|
| key | TEXT PK | |
| value | TEXT | JSON-enkoodattu |

### Indeksit

- `file_path` (UNIQUE)
- `phash`, `dhash`
- `exif_date`
- `status`
- FTS5 virtuaalitaulu: `ai_description`, `ai_tags`, `file_name`

## Indeksointiprosessi

### Säikeistysmalli

- **Vaihe 2 (EXIF + hashing):** CPU-sidottu työ, ajetaan `concurrent.futures.ThreadPoolExecutor`-poolissa (oletus: 4 säiettä)
- **Vaihe 3 (Ollama-kutsut):** I/O-sidottu työ, ajetaan `httpx.AsyncClient`-kutsuina asyncio-taskein. Rinnakkaisuus rajoitettu `asyncio.Semaphore`-arvolla (oletus: 1, koska Ollama on pullonkaula).
- **Vaihe 4 (brctl evict):** Ajetaan `asyncio.create_subprocess_exec`-kutsuina, ei blokkaa event loopia.

### Virheenkäsittely

- **Korruptoitunut tiedosto:** status="error", error_message tallennetaan, ohitetaan ja jatketaan seuraavaan
- **Ollama ei käynnissä / timeout:** 3 uudelleenyritystä 30s välein, sen jälkeen status="error". Indeksointi jatkuu muilla kuvilla.
- **Pilvilataus epäonnistuu:** macOS File Provider hoitaa uudelleenyrityksen. Jos tiedostoa ei saada luettua 60s kuluessa, status="error".
- **brctl evict epäonnistuu:** Lokitetaan varoitus, ei estä etenemistä. Tiedosto jää paikalliseksi.
- **WebSocket:** Virhelaskuri raportoidaan edistymisen yhteydessä (indeksoitu/virheet/jäljellä).

### Vaihe 1: Skannaus
- Käy läpi konfiguroidut kansiot rekursiivisesti
- Tunnistaa kuvatiedostot: jpg, jpeg, png, heic, heif, tiff, raw, cr2, nef, arw, dng
- Ohittaa jo tietokannassa olevat (file_path) paitsi jos file_size tai file_mtime on muuttunut → uudelleenindeksoidaan
- Tunnistaa poistetut tiedostot: olemassa olevat tietokantarivit joiden file_path ei enää löydy → status="missing"
- Lisää uudet rivit status="pending"

### Vaihe 2: Kevyt metadata (nopea, ThreadPoolExecutor)
Per kuva:
- Lue EXIF-tiedot (exifread)
- Laske pHash + dHash (imagehash)
- Lue tiedostokoko, dimensiot, formaatti
- Generoi thumbnail (300px pisin sivu) → tallennetaan `~/.fotoxi/thumbs/{id}.jpg`
- macOS lataa pilvivedostot automaattisesti tarvittaessa

### Vaihe 3: AI-analyysi (hidas, Ollama)
Per kuva jonka metadata on kerätty:
- Lähetä kuva Ollama vision-mallille
- Pyydä: kuvaus (suomeksi tai englanniksi), tagit, laatuarvio (jos päällä)
- Tallenna ai_description, ai_tags, ai_quality_score, ai_model
- Päivitä status="indexed"

### Vaihe 4: Pilvioptiomointi
Jos kuva on pilvipolusta (CloudStorage):
- `brctl evict <polku>` vapauttaa paikallisen kopion

### Vaihe 5: Duplikaattiryhmittely
Ajetaan kun vaihe 2 on valmis:
- **pHash-vertailu:** Hamming-etäisyys < 10 (64-bittinen hash). Kaikki parit -vertailu on O(n^2) mutta hyväksyttävä 50K kuvalla (~muutama sekunti). Optimoidaan BK-puulla tarvittaessa.
- **Burst-tunnistus:** exif_date ±5s + sama exif_camera_model
- **Ryhmien yhdistäminen:** Jos kuva A ja B ovat pHash-lähellä JA kuva B ja C ovat burst-ryhmässä, kaikki kolme yhdistetään samaan ryhmään (union). match_type kuvastaa mitkä signaalit ryhmän muodostivat.
- AI merkitsee parhaan per ryhmä (terävyys, valaistus)

### Ominaisuudet
- Edistyminen raportoidaan WebSocketilla reaaliajassa
- Pysäytettävissä ja jatkettavissa – status-kenttä pitää kirjaa
- Inkrementaalinen – uudet kuvat indeksoidaan, vanhat ohitetaan

## API-endpointit

### Kuvat
- `GET /api/images` – Hae kuvia (tekstihaku + suodattimet: q, date_from, date_to, camera, lat/lon/radius, min_quality, status, sort, order, page, limit)
- `GET /api/images/{id}` – Yksittäisen kuvan kaikki tiedot
- `GET /api/images/{id}/thumb` – Thumbnail
- `GET /api/images/{id}/full` – Täysikokoinen kuva (triggeröi automaattisen latauksen pilvestä jos evicted)

### Duplikaatit
- `GET /api/duplicates` – Duplikaattiryhmät (suodatin: status)
- `GET /api/duplicates/{id}` – Yksittäinen ryhmä kuvien tietoineen
- `POST /api/duplicates/{id}/resolve` – Käyttäjän päätös: `{ "keep": [3, 7], "reject": [4, 5, 6] }`

### Indeksointi
- `GET /api/indexer/status` – Indeksoinnin tila
- `POST /api/indexer/start` – Käynnistä indeksointi
- `POST /api/indexer/stop` – Pysäytä indeksointi

### Asetukset
- `GET /api/settings` – Nykyiset asetukset
- `PUT /api/settings` – Päivitä asetukset

### WebSocket
- `WS /api/ws` – Indeksoinnin edistyminen reaaliajassa

## Frontend-näkymät

### 1. Hakunäkymä (päänäkymä)
- Tekstihakukenttä (FTS5)
- Suodatinpalkki: päivämäärä, kamera, sijainti, laatu
- Kuvaruudukko tuloksilla, AI-kuvaukset ja EXIF-tiedot näkyvissä
- Sivutus

### 2. Duplikaattien rinnakkaisvertailu
- Kaksi kuvaa vierekkäin EXIF-tiedoilla
- AI-suositus: kumpi on parempi (terävyys, valaistus, laatu)
- Thumbnail-nauha koko ryhmästä – klikkaa vaihtaaksesi vertailtavaa
- Säilytä/Hylkää-napit per kuva
- Navigointi ryhmien välillä, edistymispalkki

### 3. Indeksointinäkymä
- Edistymispalkki ja tilastot (löydetty, indeksoitu, duplikaattiryhmät, nopeus)
- Lähdekansioiden hallinta (lisää/poista)
- Käynnistä/Pysäytä-painike
- Reaaliaikainen päivitys WebSocketilla

### 4. Asetukset
- Ollama-mallin valinta
- AI-laatuarvion kytkin (päälle/pois)
- Duplikaattitunnistuksen kynnysarvot
- Lähdekansiot

## Teknologiapino

| Kerros | Teknologia |
|--------|-----------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Tietokanta | SQLite + FTS5, aiosqlite, SQLAlchemy |
| Kuva-analyysi | Ollama (oletuksena LLaVA 7B), konfiguroitava |
| EXIF | exifread |
| Hashing | imagehash (pHash + dHash) |
| Thumbnailit | Pillow |
| Pilvioptim. | brctl evict (macOS) |
| Frontend | React 18, Vite, TypeScript |
| UI-tyylittely | Tailwind CSS |
| Tilanhallinta | React Query (server state) + zustand (UI state) |
| WebSocket | FastAPI WebSocket natiivi |

## Käynnistys

```bash
python fotoxi.py
```

Käynnistää uvicornin, tarjoilee API:n ja React-buildin samasta portista (oletus: 8000).

## Myöhemmät laajennukset

- **Vektorihaku:** sqlite-vss tai ChromaDB embedding-pohjaiselle "samankaltaiset kuvat" -haulle
- **Visuaalinen samankaltaisuushaku:** Valitse kuva → näytä samankaltaiset
- **Karttanäkymä:** GPS-koordinaattien visualisointi kartalla
- **Automaattinen albumien luonti:** AI ryhmittelee kuvat tapahtumiksi (aika + sijainti + sisältö)
- **Erillinen tag-taulu:** `image_tags` junction-taulu tehokkaampaan tagi-kyselyyn ja autocompletioniin
- **Bulk-duplikaattien ratkaisu:** "Hyväksy kaikki AI-suositukset joissa luottamus > 0.9"
- **Suomenkielinen FTS5:** Erillinen tokenizer/stemmer suomen kielelle
