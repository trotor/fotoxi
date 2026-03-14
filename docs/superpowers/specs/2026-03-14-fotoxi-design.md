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
| status | TEXT | "pending", "indexed", "kept", "rejected" |
| indexed_at | DATETIME | |
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

### Vaihe 1: Skannaus
- Käy läpi konfiguroidut kansiot rekursiivisesti
- Tunnistaa kuvatiedostot: jpg, jpeg, png, heic, heif, tiff, raw, cr2, nef, arw, dng
- Ohittaa jo tietokannassa olevat (file_path)
- Lisää uudet rivit status="pending"

### Vaihe 2: Kevyt metadata (nopea)
Per kuva:
- Lue EXIF-tiedot (exifread)
- Laske pHash + dHash (imagehash)
- Lue tiedostokoko, dimensiot, formaatti
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
- Etsi läheiset pHash-arvot (Hamming-etäisyys < kynnysarvo)
- Etsi samanaikaiset kuvat (exif_date ±5s + sama kamera)
- Yhdistä ryhmiksi
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
- `GET /api/images/{id}/full` – Täysikokoinen kuva

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
