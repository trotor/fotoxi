# Indeksointinappien yhdistäminen — toteutussuunnitelma

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Yhdistää indeksointinäkymän kolme käynnistysnappia yhdeksi laajentamalla `run_full()` kattamaan myös tiivisteet ja tuplaryhmittelyn.

**Architecture:** `run_full()` saa kaksi uutta vaihetta olemassa olevista, tähän asti vain erikseen kutsuttavista metodeista: `process_file_hashes()` heti skannauksen jälkeen (ennen cloud-evictiä, koska hashaus lukee tiedostot kokonaan) ja `group_duplicates()` metatietojen jälkeen (se tarvitsee `phash`in ja `file_hash`in). Frontendistä poistuu kaksi nappia; backendin endpointit jäävät ennalleen, koska virheiden retry käyttää `/indexer/process`-endpointia ohi UI:n.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2.0 async / pytest (`asyncio_mode = "auto"`), React 19 + TypeScript + Vite + Tailwind 4.

## Global Constraints

- Trunk-based: committoi suoraan `main`iin. Ei feature-brancheja, ei PR:iä.
- Venv on aktivoitava ennen jokaista Python-komentoa: `source .venv/bin/activate`.
- Versionnosto `pyproject.toml`:iin ja merkintä `CHANGELOG.md`:hen tässä työssä: **0.4.13 → 0.4.14**.
- `frontend/dist` rakennetaan uudelleen (`cd frontend && npm run build`) frontend-muutosten jälkeen.
- UI:ta käytetään puhelimella Tailscalen yli — muuttunut UI tarkistetaan ~390px leveydellä.
- Suomenkieliset käännökset: älä lisää uusia avaimia tässä työssä (ei tarvita).

---

### Task 1: `run_full()` kattamaan tiivisteet ja tuplaryhmittelyn

**Files:**
- Modify: `backend/indexer/orchestrator.py:984-1056` (`run_full`)
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: olemassa olevat `IndexerOrchestrator`-metodit `scan()`, `process_file_hashes()`, `process_metadata()`, `process_ai()`, `process_geocoding()`, `process_gps_inheritance()`, `group_duplicates()`, `_evict_cloud_files()` — kaikki `async def`, ei parametreja, palauttavat `None`.
- Produces: `run_full()` säilyttää signatuurinsa `async def run_full(self) -> None`. Ei uusia julkisia nimiä.

- [ ] **Step 1: Write the failing test**

Lisää `tests/test_orchestrator.py`:n loppuun. Testi korvaa kaikki vaihemetodit tallentavilla tynkillä ja tarkistaa järjestyksen. DB:hen luodaan yksi `pending`-kuva (jotta `has_metadata_work` on tosi) ja yksi `indexed`-kuva ilman `ai_description`ia (jotta `has_ai_work` on tosi), muuten `run_full` ohittaa nuo vaiheet eikä niitä näy kutsulistassa.

```python
@pytest.mark.asyncio
async def test_run_full_includes_hashing_and_grouping(tmp_path, monkeypatch):
    """run_full() hashes before eviction and groups duplicates after metadata."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()

    config = Config(
        source_dirs=[str(images_dir)],
        thumbs_dir=str(tmp_path / "thumbs"),
        thread_pool_size=1,
    )
    session_factory = await _make_session_factory(tmp_path)

    # Give run_full() both metadata work and AI work so neither branch is skipped.
    async with session_factory() as session:
        session.add(
            Image(
                file_path="/p/pending.jpg", file_name="pending.jpg", file_size=10,
                file_mtime=1.0, status="pending",
            )
        )
        session.add(
            Image(
                file_path="/p/indexed.jpg", file_name="indexed.jpg", file_size=10,
                file_mtime=2.0, status="indexed", ai_description=None,
            )
        )
        await session.commit()

    orchestrator = IndexerOrchestrator(config, session_factory)

    calls: List[str] = []

    def _recorder(name: str):
        async def _fn(*args, **kwargs):
            calls.append(name)
        return _fn

    for name in (
        "scan", "process_file_hashes", "process_metadata", "process_ai",
        "process_geocoding", "process_gps_inheritance", "group_duplicates",
        "_evict_cloud_files",
    ):
        monkeypatch.setattr(orchestrator, name, _recorder(name))

    await orchestrator.run_full()

    assert "process_file_hashes" in calls
    assert "group_duplicates" in calls
    # Hashing reads whole files, so it must precede cloud eviction.
    assert calls.index("scan") < calls.index("process_file_hashes")
    assert calls.index("process_file_hashes") < calls.index("_evict_cloud_files")
    # Grouping needs phash from the metadata phase, and must precede eviction.
    assert calls.index("process_metadata") < calls.index("group_duplicates")
    assert calls.index("group_duplicates") < calls.index("_evict_cloud_files")
    assert orchestrator.state.running is False
    assert orchestrator.state.phase == "complete"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate
python -m pytest tests/test_orchestrator.py::test_run_full_includes_hashing_and_grouping -v
```

Expected: FAIL — `assert "process_file_hashes" in calls` kaatuu, koska `run_full()` ei vielä kutsu sitä.

- [ ] **Step 3: Write minimal implementation**

Muokkaa `run_full()`:n `try`-lohkoa `backend/indexer/orchestrator.py`:ssä. Lisää tiivistevaihe heti `scan()`-lohkon jälkeen:

```python
            await self.scan()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            # File hashes before anything can evict cloud files: hashing reads
            # each file in full, and an evicted file would be re-downloaded.
            await self.process_file_hashes()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return
```

ja tuplaryhmittely `process_gps_inheritance()`-lohkon jälkeen, ennen `_evict_cloud_files()`-kutsua:

```python
            await self.process_gps_inheritance()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            # Grouping needs both phash (metadata phase) and file_hash above.
            # Resolved groups are preserved by group_duplicates() itself.
            await self.group_duplicates()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            # Evict cloud files after all processing is done
            await self._evict_cloud_files()

            self.state.phase = "complete"
```

Muuta ei kosketa — `has_metadata_work` / `has_ai_work` -rinnakkaislogiikka jää sellaisenaan.

- [ ] **Step 4: Run test to verify it passes**

```bash
source .venv/bin/activate
python -m pytest tests/test_orchestrator.py -v
```

Expected: PASS, myös aiempi `test_request_stop` pysyy vihreänä.

- [ ] **Step 5: Add the stop-event guard test**

Tämä testi kirjoitetaan **toteutuksen jälkeen**, ei ennen: ennen Step 3:a se menisi läpi tyhjästä (jos `group_duplicates()`-kutsua ei ole olemassa, väite "sitä ei kutsuttu" on triviaalisti tosi). Se on siis regressiovahti, ei ajuri.

Lisää `tests/test_orchestrator.py`:hen:

```python
@pytest.mark.asyncio
async def test_run_full_stop_skips_grouping_and_eviction(tmp_path, monkeypatch):
    """A stop requested mid-pipeline skips the remaining phases."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()

    config = Config(
        source_dirs=[str(images_dir)],
        thumbs_dir=str(tmp_path / "thumbs"),
        thread_pool_size=1,
    )
    session_factory = await _make_session_factory(tmp_path)

    async with session_factory() as session:
        session.add(
            Image(
                file_path="/p/pending.jpg", file_name="pending.jpg", file_size=10,
                file_mtime=1.0, status="pending",
            )
        )
        await session.commit()

    orchestrator = IndexerOrchestrator(config, session_factory)

    calls: List[str] = []

    def _recorder(name: str):
        async def _fn(*args, **kwargs):
            calls.append(name)
        return _fn

    for name in (
        "scan", "process_file_hashes", "process_ai", "process_geocoding",
        "process_gps_inheritance", "group_duplicates", "_evict_cloud_files",
    ):
        monkeypatch.setattr(orchestrator, name, _recorder(name))

    # Metadata phase asks to stop; everything after it must be skipped.
    async def _metadata_then_stop(*args, **kwargs):
        calls.append("process_metadata")
        orchestrator.request_stop()

    monkeypatch.setattr(orchestrator, "process_metadata", _metadata_then_stop)

    await orchestrator.run_full()

    assert "process_metadata" in calls
    assert "group_duplicates" not in calls
    assert "_evict_cloud_files" not in calls
    assert orchestrator.state.running is False
    assert orchestrator.state.phase == "idle"
```

- [ ] **Step 6: Add the incrementality test**

Sama vahti tiivistevaiheen inkrementaalisuudelle — se on koko suunnitelman perustelu ("toistoajo on halpa"). `process_file_hashes()` palaa heti, jos yhdelläkään kuvalla ei ole puuttuvaa `file_hash`ia.

```python
@pytest.mark.asyncio
async def test_process_file_hashes_is_noop_when_all_hashed(tmp_path):
    """process_file_hashes() does no work when every image already has a hash."""
    config = Config(
        source_dirs=[str(tmp_path / "photos")],
        thumbs_dir=str(tmp_path / "thumbs"),
    )
    session_factory = await _make_session_factory(tmp_path)

    async with session_factory() as session:
        session.add(
            Image(
                file_path="/p/done.jpg", file_name="done.jpg", file_size=10,
                file_mtime=1.0, status="indexed", file_hash="abc123",
            )
        )
        await session.commit()

    orchestrator = IndexerOrchestrator(config, session_factory)
    orchestrator.state.total = 0
    await orchestrator.process_file_hashes()

    # Early return leaves the counters untouched — nothing was queued for hashing.
    assert orchestrator.state.total == 0
    assert orchestrator.state.processed == 0
```

- [ ] **Step 7: Run the full backend suite**

```bash
source .venv/bin/activate
python -m pytest -q tests/
```

Expected: 108 passed (105 aiempaa + 3 uutta).

- [ ] **Step 8: Commit**

```bash
git add backend/indexer/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: run_full() now also hashes files and groups duplicates"
```

---

### Task 2: Poista ylimääräiset napit indeksointinäkymästä

**Files:**
- Modify: `frontend/src/pages/Indexing.tsx:230-268` (nappirivi), `frontend/src/pages/Indexing.tsx:6-9` (importit)
- Modify: `frontend/src/api.ts:308-311` (`computeHashes`)

**Interfaces:**
- Consumes: `startIndexer()`, `stopIndexer()`, `getIndexerStatus()` `frontend/src/api.ts`:stä (ennallaan). `processOnly()` jää `api.ts`:ään, koska `ErrorsPanel` käyttää sitä.
- Produces: ei uusia vientejä. `computeHashes()` poistuu `api.ts`:n julkisesta pinnasta.

**Huom:** frontendissä ei ole testiajuria (`package.json` scripts: `dev`, `build`, `lint`, `preview`). Varmistus on siis lint + tyypitys + silmämääräinen tarkistus, ei yksikkötesti.

- [ ] **Step 1: Poista nappirivin sininen ja violetti nappi**

`frontend/src/pages/Indexing.tsx`, korvaa rivit 230-268 (`<div className="flex flex-wrap gap-2">` … `</div>`) tällä:

```tsx
          <div className="flex flex-wrap gap-2">
            <button
              onClick={handleStartStop}
              disabled={stopping}
              className={`px-5 py-2 rounded text-sm font-medium transition-colors ${
                stopping
                  ? 'bg-yellow-800 text-yellow-200 cursor-wait animate-pulse'
                  : status.running
                    ? 'bg-red-800 hover:bg-red-700 text-white'
                    : 'bg-green-700 hover:bg-green-600 text-white'
              }`}
            >
              {stopping ? t('idx.stopping') : status.running ? t('idx.stop') : t('idx.start_scan')}
            </button>
          </div>
```

Koko `{!status.running && (<> … </>)}` -lohko poistuu.

- [ ] **Step 2: Siivoa importit**

`frontend/src/pages/Indexing.tsx` rivit 6-9: poista `computeHashes` importtilistasta. **Jätä `processOnly`** — `ErrorsPanel.handleRetry` käyttää sitä rivillä 51.

- [ ] **Step 3: Poista käyttämätön API-wrapper**

`frontend/src/api.ts`, poista rivit 308-311:

```ts
export async function computeHashes(): Promise<void> {
  const res = await fetch(`${BASE}/indexer/compute-hashes`, { method: 'POST' })
  if (!res.ok) throw new Error(`Compute hashes failed: ${res.status}`)
}
```

Backendin `/indexer/compute-hashes` **jää paikoilleen** — se on halpa säilyttää ja kätevä manuaaliajoon curlilla.

- [ ] **Step 4: Verify lint and types**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

Expected: ei uusia virheitä. Lähtötilanteessa on 6 ennestään olemassa olevaa ESLint-virhettä ja 4 varoitusta — niiden määrä ei saa kasvaa. Erityisesti: ei `no-unused-vars`-virhettä `processOnly`- tai `computeHashes`-nimistä.

- [ ] **Step 5: Verify in the running app at phone width**

Dev-serverit: backend `python fotoxi.py serve` (portti 8001), frontend `cd frontend && npm run dev -- --host --port 5174`.

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5174/api/indexer/status
```

Expected: `200`.

Avaa `http://localhost:5174/indexing` 390px leveydellä ja tarkista silmämääräisesti:
- Tilakortissa on **yksi** nappi ("Käynnistä skannaus"), ei sinistä eikä violettia.
- Nappi mahtuu riville ilman rivinvaihtoa.
- Napin painaminen käynnistää ajon ja teksti vaihtuu muotoon "Pysäytä".
- Vaiheteksti käy läpi myös "hashing"- ja "grouping"-vaiheet ilman raakaa avainnimeä (käännökset ovat jo `PHASE_KEYS`-taulukossa, `Indexing.tsx:21-33`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Indexing.tsx frontend/src/api.ts
git commit -m "ux: single indexing button, drop process/hash buttons"
```

---

### Task 3: Versionnosto, changelog ja build

**Files:**
- Modify: `pyproject.toml` (`version`)
- Modify: `CHANGELOG.md`
- Build: `frontend/dist/`

**Interfaces:**
- Consumes: Task 1:n ja Task 2:n muutokset.
- Produces: julkaisukelpoinen 0.4.14.

- [ ] **Step 1: Bump version**

`pyproject.toml`: `version = "0.4.13"` → `version = "0.4.14"`.

- [ ] **Step 2: Add changelog entry**

Lisää `CHANGELOG.md`:hen heti `# Changelog`-otsikon ja johdantorivin jälkeen, ennen `## [0.4.13]`-lohkoa:

CHANGELOG.md on englanniksi — kirjoita merkintä samalla tyylillä kuin aiemmat lohkot:

```markdown
## [0.4.14] - 2026-07-26

### Changed
- **One indexing button instead of three** — "Process missing" and "Compute hashes" are gone from the Indexing view. `run_full()` now covers the whole pipeline: scan → file hashes → metadata + AI → geocoding → GPS inheritance → duplicate grouping → cloud eviction. Hashing runs before eviction (it reads each file in full, and an evicted cloud file would be re-downloaded) and grouping runs after metadata (it needs both `phash` and `file_hash`). Previously neither hashing nor duplicate grouping belonged to any automatic pipeline — they were reachable only from their own buttons. (`orchestrator.py`, `Indexing.tsx`)

### Removed
- Unused `computeHashes()` helper in `api.ts`. The backend `/indexer/compute-hashes` route stays for manual runs, as does `/indexer/process`, which the error-retry flow still calls.
```

- [ ] **Step 3: Rebuild the frontend bundle**

```bash
cd frontend && npm run build
```

Expected: build menee läpi, `frontend/dist/index.html` ja `frontend/dist/assets/*` saavat uuden aikaleiman.

- [ ] **Step 4: Run the full suite once more**

```bash
source .venv/bin/activate
python -m pytest -q tests/
```

Expected: 108 passed. `tests/test_version.py` lukee version `pyproject.toml`:sta, joten se vahvistaa noston.

- [ ] **Step 5: Commit and push**

```bash
git add pyproject.toml CHANGELOG.md frontend/dist
git commit -m "chore: release v0.4.14"
git push
```

- [ ] **Step 6: Restart the production service**

Jos launchd-palvelu on ajossa, se pyörittää vanhaa koodia. Uudelleenkäynnistys:

```bash
launchctl kickstart -k gui/$(id -u)/com.fotoxi.serve
```

Jos palvelu on unloadattu dev-työn ajaksi, lataa se takaisin:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.fotoxi.serve.plist
```

Expected: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/api/version` → `200`, ja versio on `0.4.14`. Huom: PWA:n service worker cachettaa vanhan buildin, joten selain voi vaatia pari uudelleenlatausta.

---

## Muistiinpano seuraavalle työlle (ei tässä laajuudessa)

`group_duplicates()` ajetaan nyt jokaisella indeksoinnilla ja se lataa kaikki kuvat, joilla on `phash` tai `file_hash` — nykykirjastolla enintään noin 38 000 riviä. Jos täysi ajo alkaa tuntua hitaalta, luonteva jatko on ohittaa ryhmittely silloin kun skannaus ei löytänyt uusia tai muuttuneita tiedostoja.
