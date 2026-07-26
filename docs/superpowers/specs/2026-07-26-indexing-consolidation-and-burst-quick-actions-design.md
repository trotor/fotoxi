# Indeksoinnin yhdistäminen ja sarjakuvien pikavalinta

**Päivämäärä:** 2026-07-26
**Tila:** Hyväksytty, odottaa toteutussuunnitelmaa

Kaksi toisistaan riippumatonta muutosta, jotka voidaan toteuttaa ja julkaista erikseen:

1. Indeksointinäkymän kolme käynnistysnappia yhdistetään yhdeksi.
2. Tuplanäkymän sarjakuvat saavat "Säilytä suositeltu" -pikavalinnan ja peruutuksen.

---

## Lähtötilanne

### Indeksointinapit

Indeksointinäkymässä (`frontend/src/pages/Indexing.tsx:230-268`) on kolme nappia:

| Nappi | Endpoint | Ajaa |
|---|---|---|
| Käsittele puuttuvat (sininen) | `/indexer/process` | metatiedot → AI → geokoodaus → GPS-perintä → evict |
| Laske tiivisteet (violetti) | `/indexer/compute-hashes` | vain SHA-256 |
| Käynnistä skannaus (vihreä) | `/indexer/start` → `run_full()` | skannaus → metatiedot+AI → geokoodaus → GPS-perintä → evict |

Olennaiset havainnot:

- **Vihreä on sinisen supersetti.** `run_full()` (`backend/indexer/orchestrator.py:984`) ajaa saman putken kuin `/indexer/process` (`backend/api/routes.py:1051`), edellä vain `scan()`. Sininen nappi on siis aidosti tarpeeton.
- **Tiivisteet eivät ole kummassakaan putkessa.** `process_file_hashes()` on kutsuttavissa vain violetista napista tai CLI:stä (`fotoxi.py:522`). Nappi ei ole päällekkäinen vaan orpo — sen poistaminen ilman yhdistämistä veisi SHA-256:n pois UI:sta kokonaan.
- **Tuplaryhmittely ei ole `run_full()`:ssä.** `group_duplicates()` ajetaan vain käynnistyksessä, jos `auto_process_on_start` on päällä (`backend/main.py:129`), tai Tuplat-sivun napista.
- **Toistuva ryhmittely on turvallista.** `group_duplicates()` poistaa vain ratkaisemattomat ryhmät ja jättää käyttäjän päätökset koskematta (`orchestrator.py:875-906`).
- **`processOnly()` on käytössä muualla.** Virheiden uudelleenyritys kutsuu sitä (`Indexing.tsx:51`, `retryErrors()` jälkeen) nimenomaan siksi, että se ei skannaa kansioita.

### Tuplien pikavalinnat

Tuplanäkymässä (`frontend/src/pages/Duplicates.tsx:442-473`) sarjakuvaryhmän päätoiminto on iso vihreä **Säilytä kaikki (N)**. Sen alla on pieni alleviivattu tekstilinkki **Pienennä parhaaseen**, joka kutsuu `handleAutoConfirm()` (`Duplicates.tsx:281-286`): säilyttää suositellun, hylkää loput, siirtyy seuraavaan ryhmään.

Olennaiset havainnot:

- Toiminto **on jo olemassa**, mutta se on piilotettu tekstilinkiksi.
- **Tuplat-sivulla ei ole vahvistusta eikä peruutusta.** `resolveAndNext()` (`Duplicates.tsx:259-278`) kutsuu mutaatiota suoraan. Yksi klikkaus pientä linkkiä hylkää ruudut peruuttamattomasti.
- **Toast+undo-infra on olemassa mutta kytkemättä.** `UIProvider`/`useToast` (0.4.11) on käytössä Haku-sivulla (`Search.tsx:693-705`), ei Tuplat-sivulla.
- **DB ei säilytä edellistä statusta.** `resolve_duplicate_group()` (`backend/db/queries.py:240`) ylikirjoittaa `image.status` arvoihin `kept`/`rejected` säilyttämättä aiempaa. Peruutus vaatii siis, että kutsuja muistaa entiset tilat — sama kuvio kuin Haku-sivun undossa.

---

## Osa 1: Yksi indeksointinappi

### Putken laajuus

`run_full()` laajenee kattamaan koko putken:

```
skannaus → tiivisteet → metatiedot + AI (rinnakkain) → geokoodaus
        → GPS-perintä → tuplaryhmittely → cloud-evict
```

Järjestyksen perustelut:

- **Tiivisteet heti skannauksen jälkeen.** `process_file_hashes()` lukee tiedostot kokonaisuudessaan. Pilvitiedostot on hashattava ennen `_evict_cloud_files()`-vaihetta, muuten evictattu tiedosto ladataan uudelleen.
- **Tuplaryhmittely metatietojen jälkeen, ennen evictiä.** Se tarvitsee sekä `phash`in (syntyy metatietovaiheessa) että `file_hash`in.
- Nykyinen `has_metadata_work` / `has_ai_work` -rinnakkaislogiikka säilyy muuttumattomana.
- `_stop_event`-tarkistus jokaisen vaiheen välissä, kuten nykyisin.

Jokainen vaihe on inkrementaalinen ja ohittaa jo tehdyn työn, joten toistoajo uudella kirjastolla on halpa.

### Endpointit

| Endpoint | Kohtalo | Perustelu |
|---|---|---|
| `/indexer/start` | Jää | UI:n ainoa käynnistyspolku |
| `/indexer/process` | Jää | Virheiden retry käyttää sitä; ei enää nappia |
| `/indexer/compute-hashes` | Jää | Halpa säilyttää, kätevä manuaaliajoon |
| `/indexer/find-duplicates` | Jää | Tuplat-sivu käyttää (`Duplicates.tsx:157`) |

`computeHashes()` poistetaan `frontend/src/api.ts`:stä käyttämättömänä. `processOnly()` jää, koska `ErrorsPanel` käyttää sitä.

### Frontend

- Tilakortista (`Indexing.tsx:230-268`) poistuvat sininen ja violetti nappi.
- Jäljelle jää vihreä **Indeksoi** / punainen **Pysäytä** (nykyinen `handleStartStop`).
- `PHASE_KEYS` (`Indexing.tsx:21-33`) kattaa jo `hashing`- ja `grouping`-vaiheet, ja käännökset ovat olemassa. Edistymispalkki toimii sellaisenaan.
- Nappirivi lyhenee kahdella napilla, mikä poistaa 390px-leveyden rivinvaihdon tarpeen.

### Tiedostetut seuraukset

Tuplaryhmittely ajetaan nyt jokaisella indeksoinnilla. `group_duplicates()` lataa kaikki kuvat, joilla on `phash` tai `file_hash` ja joiden status ei ole `rejected`/`missing`/`error` — nykyisellä kirjastolla enintään noin 38 000 kuvaa (`indexed` 33 433 + `kept` 4 495; tiivisteettömät jäävät pois). Täysi ajo pitenee tämän verran. Ratkaistut ryhmät säilyvät, joten käyttäjän työ ei mene hukkaan.

---

## Osa 2: Sarjakuvien pikavalinta ja peruutus

**Rajaus:** vain sarjakuvat (`isBurst`). Kopioryhmien iso vihreä nappi on jo "Säilytä suositeltu", eikä siihen kosketa.

### Käyttöliittymä

Sarjakuvaryhmälle kaksi rinnakkaista päänappia nykyisen yhden sijaan:

```
┌────────────────────┐ ┌──────────────────────────┐
│  Säilytä kaikki    │ │  Säilytä suositeltu      │
│       (8)          │ │     (hylkää 7)           │
└────────────────────┘ └──────────────────────────┘
```

- Puhelimella napit pinoutuvat (`flex-wrap`).
- Pieni alleviivattu **Pienennä parhaaseen** -linkki poistuu; nappi korvaa sen.
- Sarjakuvavaroitus (`dup.burst_note`) säilyy.

Hylkäävän pikavalinnan jälkeen toast:

```
Hylkäsin 7 ruutua              [ Kumoa ]
```

**Kumoa** palauttaa tilat ja palaa kyseiseen ryhmään.

### Peruutus

Uusi endpoint `POST /duplicates/{group_id}/unresolve`, runko `{"statuses": {"<image_id>": "<status>"}}`:

- nollaa `member.user_choice = None` ryhmän kaikilta jäseniltä
- palauttaa `image.status` annettuihin arvoihin
- tyhjentää `kept_at` / `rejected_at` niiltä kuvilta, joiden status palautuu

Kutsuja lähettää entiset statukset, koska DB ei niitä säilytä. Frontend lukee ne `members`-listasta ennen ratkaisua — sama kuvio kuin `Search.tsx:693`.

`UIProvider`/`useToast` kytketään Tuplat-sivulle.

### Asetus

Uusi kenttä `backend/config.py`:hin:

```python
dup_confirm_quick_actions: bool = False
```

Päällä ollessaan pikavalinta näyttää ensin vahvistusdialogin (olemassa oleva in-app confirm, 0.4.11). Oletuksena pois, jolloin undo on ainoa suoja. Kenttä näkyy Asetukset-sivulla valintaruutuna.

### Tiedostettu rajaus

Peruutus palauttaa kuvien statukset ja ryhmän ratkaisemattomaksi, muttei sivutuksen tilaa. Jos ryhmä oli sivun viimeinen ja sivutus ehti vaihtua, käyttäjä palaa ryhmään mutta listan kohta voi olla eri.

---

## Testaus

**Backend (pytest)**

- `run_full()` ajaa vaiheet oikeassa järjestyksessä ja tiivisteet ennen evictiä.
- `run_full()` keskeytyy `_stop_event`:stä jokaisen uuden vaiheen kohdalla.
- Toistuva `run_full()` ei tee turhaa työtä, kun kaikki on jo indeksoitu.
- `POST /duplicates/{id}/unresolve` palauttaa statukset ja nollaa `user_choice`.
- `unresolve` tuntemattomalla ryhmällä palauttaa 404.

**Frontend**

- Lint ja `tsc --noEmit` puhtaina.
- Silmämääräinen tarkistus 390px-leveydellä: indeksointinäkymän nappirivi ja sarjakuvan kaksi päänappia.
- Toast + Kumoa palauttaa ruudut näkyviin.

## Julkaisu

Molemmat osat: versionnosto `pyproject.toml`:iin ja merkintä `CHANGELOG.md`:hen. `frontend/dist` rakennetaan uudelleen (`npm run build`). Osat voidaan julkaista erillisinä versioina.
