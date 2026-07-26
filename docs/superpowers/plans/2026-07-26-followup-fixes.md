# Katselmointien jälkityöt — toteutussuunnitelma

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sulkea seitsemän GitHub-issueta, jotka 0.4.14–0.4.17:n katselmoinnit paljastivat: tuplanäkymän peruutus kaikille hylkäystoiminnoille, rehellinen tila vanhentuneelle ryhmälle ja asetuksille, skannerin muutostunnistus, tuplaryhmittelyn pysäytettävyys, ja suomenkielisten merkkijonojen ääkköset.

**Architecture:** Neljä toisistaan riippumatonta rypästä. Painavin on #59: `resolveAndNext` yleistetään niin että peruutus syntyy jokaisesta hylkäävästä toiminnosta, jolloin nykyinen `handleBurstReduce`-erikoistapaus kutistuu — 0.4.17:ssä syntyneet `afterResolve` ja `runUndo` tekevät tästä nyt vähemmän koodia kuin se korvaa. Loput ovat rajattuja korjauksia backendin `scan()`- ja `group_duplicates()`-funktioihin sekä puhtaita merkkijonomuutoksia.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2.0 async / pytest (`asyncio_mode = "auto"`), React 19 + TypeScript + TanStack Query + Vite + Tailwind 4.

## Global Constraints

- Trunk-based: committoi suoraan `main`iin. Ei feature-brancheja, ei PR:iä.
- Venv on aktivoitava ennen jokaista Python-komentoa: `source .venv/bin/activate`.
- Versionnosto tässä työssä: **0.4.17 → 0.4.18**. Vain viimeinen tehtävä nostaa version ja koskee `CHANGELOG.md`:hen.
- `CHANGELOG.md` kirjoitetaan **englanniksi**, kuten kaikki aiemmat merkinnät.
- `frontend/dist` on gitignoressa (`frontend/.gitignore:11`) eikä sitä committoida. Vain julkaisutehtävä ajaa `npm run build`.
- Lavasta tiedostot nimeltä. **Älä koskaan `git add -A` tai `git add .`** — repon juuressa on seuraamaton `package-lock.json`, jota ei committoida eikä poisteta.
- Lähtötaso: backend **116 testiä läpi**; `npm run lint` 6 virhettä ja 4 varoitusta; `npx tsc --noEmit` puhdas. Älä kasvata lint-lukuja äläkä korjaa niitä ennestään olevia virheitä.
- Suomen kielessä käytetään burst-ryhmästä sanaa **kuvasarja**, ei *sarjakuva* (= piirretty sarjakuva). Tämä on käyttäjän päätös.
- **Tuotantopalvelu `com.fotoxi.serve` on käynnissä ja tarjoilee oikeaa 64k kuvan kirjastoa portissa 8001.** Älä pysäytä sitä. Jos tarvitset dev-serverit, pyydä ohjaajalta. Testit käyttävät omia väliaikaiskantojaan.

---

### Task 1: Suomenkielisten merkkijonojen ääkköset (#56)

**Files:**
- Modify: `frontend/src/i18n/fi.json`
- Modify: `frontend/src/i18n/en.json` (vain käyttämättömien avainten poisto)

**Interfaces:**
- Consumes: ei mitään aiemmasta tehtävästä.
- Produces: ei uusia avaimia. Kaksi avainta poistuu molemmista tiedostoista: `idx.process_missing` ja `idx.compute_hashes` (niiden ainoat käyttöpaikat poistuivat 0.4.14:ssä).

Tämä on puhdas merkkijonotehtävä: ei logiikkaa, ei komponentteja.

- [ ] **Step 1: Korjaa ääkköset `fi.json`:ssä**

Nämä 28 arvoa ovat menettäneet ä/ö-merkkinsä. Korjaa jokainen. Vasemmalla avain, oikealla oikea arvo:

```
search.show                = "Näytä:"
search.kept                = "Säilytetyt"
search.sort                = "Järjestä:"
search.keep_next           = "Säilytä & seur."
search.reject_next         = "Hävitä & seur."
search.click_unkeep        = "Klikkaa poistaaksesi säilytys-merkintä"
status.kept                = "Säilytetty"
stats.show_all             = "Näytä kaikki"
stats.show_less            = "Näytä vähemmän"
stats.show_year            = "Näytä koko vuosi"
idx.start_scan             = "Skannaa & käsittele"
idx.kept_label             = "Säilytetty"
dup.group                  = "Ryhmä"
dup.keep_recommended       = "Säilytä suositeltu"
dup.keep_recommended_full  = "Säilytä suositeltu & seuraava"
dup.keep_all               = "Säilytä kaikki"
dup.reject_all             = "Hävitä kaikki"
dup.keep_folder            = "Säilytä"
dup.keeping                = "Säilytetään"
dup.mode_keep              = "Säilytettävä"
dup.kept_badge             = "säilytetään"
dup.reduce_to_best         = "Jätä vain paras"
```

Kolme vaativat myös sanavalinnan tai kieliopin korjauksen samalla:

```
dup.reject         = "Hylkää"
```
Huom: tämä oli `"hylkaa"` pienellä. Se esiintyi ennen vain lauseen keskellä muodossa `(hylkaa 3)`, mutta 0.4.16:sta lähtien se on tuhoavan punaisen vahvistuspainikkeen teksti (`Duplicates.tsx:317`), joten se tarvitsee ison alkukirjaimen.

```
common.confirm_reject = "Vahvista (hylkää"
```
Arvo on tarkoituksella keskeneräinen lause — kutsupaikka liittää siihen lukumäärän ja sulkevan sulun. Älä "korjaa" rakennetta, vain ääkköset.

```
dup.burst_keep_all = "Säilytä kaikki (sarja)"
```

- [ ] **Step 2: Yhtenäistä burst-termi `fi.json`:ssä**

Kaksi arvoa käyttää sanaa *sarjakuva*, joka tarkoittaa suomeksi piirrettyä sarjakuvaa. Näistä käyttäjä omaksui termin. Korvaa **kuvasarja**-muodoilla ja korjaa samalla `dup.cleanup_hint`:n kielioppivirhe ("ei koskettaa" → "ei kosketa"):

```
dup.burst_note   = "Kuvasarjat ovat tarkoituksellisia otoksia — oletuksena säilytetään kaikki."
dup.cleanup_hint = "Poistaa tarkat ja visuaaliset kopiot automaattisesti (säilyttää parhaan). Kuvasarjoja ei kosketa."
```

Älä koske avaimeen, jonka arvo on `"Sarjakuvaus"` — se on `match_type`-suodattimen nimi ja tarkoittaa sarjakuvausta eli burst-kuvaustapaa, mikä on oikein.

- [ ] **Step 3: Poista käyttämättömät avaimet**

Poista `idx.process_missing` ja `idx.compute_hashes` **sekä** `fi.json`:sta että `en.json`:sta. Niiden ainoat käyttöpaikat poistuivat 0.4.14:ssä.

Varmista ensin, ettei niihin ole viittauksia:

```bash
cd frontend && grep -rn "idx.process_missing\|idx.compute_hashes" src/
```

Expected: ei osumia `src/`-hakemistosta (JSON-tiedostot eivät ole siellä).

Jätä `dup.reduce_to_best` paikoilleen molempiin tiedostoihin, vaikka se on käyttämätön. Se on kuvasarjojen "jätä vain paras" -sanamuoto, ja toiminto on yhä olemassa — vain sen tekstilinkki poistui 0.4.16:ssa. Se on todennäköinen paluu, toisin kuin poistetut napit.

Sama koskee `dup.frames_rejected`-avainta, joka jää käyttämättömäksi Task 3:ssa: älä poista sitä siinäkään.

- [ ] **Step 4: Varmista että molemmat kielitiedostot ovat rakenteeltaan yhtenevät**

```bash
cd /Users/teroronkko/code/fotoxi && python3 -c "
import json
fi=json.load(open('frontend/src/i18n/fi.json')); en=json.load(open('frontend/src/i18n/en.json'))
only_fi=sorted(set(fi)-set(en)); only_en=sorted(set(en)-set(fi))
print('only in fi:', only_fi)
print('only in en:', only_en)
print('counts:', len(fi), len(en))
"
```

Expected: molemmat listat tyhjiä ja lukumäärät yhtä suuret. Jos eivät ole, epäsuhta on ennestään olemassa — raportoi se äläkä korjaa tässä.

- [ ] **Step 5: Varmista käännös ja lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: tsc puhdas; lint 6 virhettä / 4 varoitusta. Rikkinäinen JSON (esim. karannut pilkku) kaataisi tsc:n, joten tämä on samalla syntaksitarkistus.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/i18n/fi.json frontend/src/i18n/en.json
git commit -m "i18n: restore Finnish diacritics, use kuvasarja for bursts (#56)"
```

---

### Task 2: Rehellinen tila — vanhentunut ryhmä ja asetusten voimaantulo (#52, #60)

**Files:**
- Modify: `backend/db/queries.py` (`resolve_duplicate_group`)
- Modify: `backend/api/routes.py` (`resolve_duplicate`-endpoint)
- Modify: `frontend/src/pages/Settings.tsx` (tallennuksen `onSuccess`, rivi ~34)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: ei mitään Task 1:stä.
- Produces: `resolve_duplicate_group(...)` palauttaa nyt `bool` (`False` jos ryhmää ei ole tai sillä ei ole yhtään annettua jäsentä). `POST /api/duplicates/{group_id}/resolve` palauttaa 404 samassa tilanteessa. Task 3 nojaa tähän 404:ään.

Kaksi pientä korjausta, jotka molemmat poistavat tilanteen, jossa käyttöliittymä näyttää onnistuneelta vaikka mitään ei tapahtunut.

- [ ] **Step 1: Kirjoita kaatuva testi**

Lisää `tests/test_api.py`:hen. `group_duplicates()` poistaa ja luo uudelleen ratkaisemattomat ryhmät jokaisella indeksoinnilla antaen niille uudet id:t, joten puhelimella triagea tekevä käyttäjä voi lähettää ratkaisun ryhmälle, jota ei enää ole.

```python
@pytest.mark.asyncio
async def test_resolve_unknown_group_returns_404(client):
    """POST /api/duplicates/{id}/resolve must not silently succeed for a stale group."""
    resp = await client.post(
        "/api/duplicates/99999/resolve", json={"keep": [1], "reject": [2]}
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Aja testi ja varmista että se kaatuu**

```bash
source .venv/bin/activate
python -m pytest tests/test_api.py::test_resolve_unknown_group_returns_404 -v
```

Expected: FAIL — palautuu 200, koska endpoint palauttaa `{"status": "resolved"}` ehdoitta.

- [ ] **Step 3: Palauta tieto siitä, löytyikö ryhmä**

`backend/db/queries.py`, `resolve_duplicate_group`: muuta paluutyypiksi `bool`. Funktio hakee jo jäsenet muuttujaan `members`; jos lista on tyhjä, mitään ei muutettu. Lisää heti `members`-haun jälkeen:

```python
    if not members:
        return False
```

ja funktion loppuun, `await session.commit()`-rivin jälkeen:

```python
    return True
```

Päivitä funktion signatuuri `-> bool` ja docstringiin rivi siitä, että `False` tarkoittaa "ryhmää ei ole tai sillä ei ole yhtään annetuista jäsenistä".

- [ ] **Step 4: Palauta 404 endpointista**

`backend/api/routes.py:912-924`, `resolve_duplicate`-endpoint (juuri `UnresolveBody`-luokan yläpuolella). Muuta se ottamaan paluuarvo vastaan:

```python
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        found = await resolve_duplicate_group(
            session=session,
            group_id=group_id,
            keep_ids=body.keep,
            reject_ids=body.reject,
        )
    if not found:
        raise HTTPException(status_code=404, detail="Duplicate group not found")
    return {"status": "resolved"}
```

- [ ] **Step 5: Aja testit**

```bash
source .venv/bin/activate
python -m pytest tests/test_api.py -v
```

Expected: PASS, mukaan lukien olemassa olevat `test_unresolve_duplicate_group` ja `test_bulk_resolve_duplicates_dry_run`.

- [ ] **Step 6: Mitätöi asetuskysely tallennuksen jälkeen**

`frontend/src/pages/Settings.tsx`. Tallennusmutaatio on rivillä ~32 ja sen `onSuccess` rivillä ~34. `App.tsx:40` asettaa `staleTime: 30_000`, joten ilman mitätöintiä juuri tallennettu asetus ei näy muualla 30 sekuntiin. `dup_confirm_quick_actions` on ensimmäinen asetus, jonka vanhentuminen muuttaa **tuhoavan** toiminnon käytöstä.

Tuo `useQueryClient` `@tanstack/react-query`:stä (`useQuery` ja `useMutation` tuodaan jo rivillä 2), ota komponentissa `const queryClient = useQueryClient()`, ja lisää mutaation `onSuccess`-käsittelijään:

```tsx
      queryClient.invalidateQueries({ queryKey: ['settings'] })
```

Säilytä kaikki muu, mitä `onSuccess` jo tekee.

- [ ] **Step 7: Varmista frontend**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: tsc puhdas; lint 6 / 4.

- [ ] **Step 8: Commit**

```bash
git add backend/db/queries.py backend/api/routes.py tests/test_api.py frontend/src/pages/Settings.tsx
git commit -m "fix: 404 on stale duplicate group resolve, refresh settings after save (#52, #60)"
```

---

### Task 3: Peruutus kaikille hylkääville toiminnoille (#59)

**Files:**
- Modify: `frontend/src/pages/Duplicates.tsx` (`resolveAndNext` ja viisi käsittelijää, rivit ~283-397)
- Modify: `frontend/src/i18n/fi.json`, `frontend/src/i18n/en.json`

**Interfaces:**
- Consumes: Task 2:n 404 vanhentuneelle ryhmälle. `unresolveDuplicateGroup(groupId, statuses)` `api.ts`:stä (olemassa). `useToast()`:n `toast` ja `confirm` (olemassa). `afterResolve(resolvedGroupId)` (olemassa, rivi 270).
- Produces: `resolveAndNext(keepIds, rejectIds)` on nyt `async` ja tarjoaa peruutuksen itse. Kolmas `onDone`-parametri poistuu — sitä ei enää tarvita.

Tämä on suunnitelman painavin osa. Nykyisin peruutuksen saa vain `handleBurstReduce`, joka on kuvasarjojen **turvallisin** hylkäystoiminto. `handleRejectAll` hylkää koko ryhmän ilman peruutusta, ja `handleAutoConfirm` on kopioryhmien pääpainike. Siirtämällä talteenoton ja toastin `resolveAndNext`iin kaikki viisi saavat peruutuksen, ja `handleBurstReduce` kutistuu.

**Sääntö:** peruutus tarjotaan aina kun `rejectIds.length > 0`. `handleKeepAll` ei hylkää mitään, joten se ei saa toastia — sillä ei ole mitään peruttavaa.

- [ ] **Step 1: Lisää yleinen käännösavain**

Nykyinen `dup.frames_rejected` ("ruutua hylätty") on kuvasarjasanastoa. Kopioryhmässä oikea sana on "kuvaa". Lisää yleinen avain ja jätä vanha paikoilleen (Task 1 saattoi jo korjata sen ääkköset).

`frontend/src/i18n/fi.json`:

```json
  "dup.images_rejected": "kuvaa hylätty",
```

`frontend/src/i18n/en.json`:

```json
  "dup.images_rejected": "images rejected",
```

- [ ] **Step 2: Yleistä `resolveAndNext`**

`frontend/src/pages/Duplicates.tsx`, korvaa nykyinen `resolveAndNext` (rivit 283-297) tällä. Se ottaa `handleBurstReduce`:n `mutateAsync`-kuvion ja peruutuksen, ja tarjoaa ne kaikille kutsujille:

```tsx
  /** Resolve with given keep/reject and move to next.
   *
   *  Uses mutateAsync rather than mutate's onSuccess callback: TanStack Query v5
   *  skips mutate-scoped callbacks if the component unmounts before the mutation
   *  settles, but the mutation still lands — which would silently drop the toast
   *  and the undo affordance.
   *
   *  Any resolution that rejects at least one image offers an undo. The database
   *  does not keep the pre-resolution status, so it is captured here beforehand. */
  async function resolveAndNext(keepIds: number[], rejectIds: number[]) {
    if (!group) return
    const groupId = group.id

    const previous: Record<number, string> = {}
    members.forEach(m => {
      if (m.image?.status) previous[m.image_id] = m.image.status
    })

    try {
      await resolveMutation.mutateAsync({ groupId, keepIds, rejectIds })
    } catch {
      return // the mutation-level onError already surfaced the failure
    }
    afterResolve(groupId)

    if (rejectIds.length === 0) return // nothing rejected, nothing to undo

    const runUndo = async () => {
      try {
        await unresolveDuplicateGroup(groupId, previous)
        queryClient.invalidateQueries({ queryKey: ['duplicates'] })
      } catch {
        toast(t('dup.undo_failed'), {
          variant: 'error',
          duration: 12000,
          action: { label: t('common.undo'), onClick: runUndo },
        })
      }
    }
    toast(`${rejectIds.length} ${t('dup.images_rejected')}`, {
      duration: 12000,
      action: { label: t('common.undo'), onClick: runUndo },
    })
  }
```

- [ ] **Step 3: Kutista `handleBurstReduce`**

Korvaa koko nykyinen `handleBurstReduce` (rivit 307-358) tällä. Kaikki talteenotto, `mutateAsync`, `afterResolve`, `runUndo` ja toast siirtyivät `resolveAndNext`iin; jäljelle jää vahvistusportti ja kutsu:

```tsx
  /** Burst quick action: keep the recommended frame, reject the rest. */
  async function handleBurstReduce() {
    if (!group) return
    const rejectIds = members
      .filter(m => m.image_id !== suggestedBestId)
      .map(m => m.image_id)
    if (rejectIds.length === 0) return

    if (settings?.dup_confirm_quick_actions) {
      const ok = await confirm(t('dup.confirm_reduce'), {
        confirmLabel: t('dup.reject'),
        danger: true,
      })
      if (!ok) return
    }

    await resolveAndNext([suggestedBestId], rejectIds)
  }
```

- [ ] **Step 4: Muuta neljä muuta käsittelijää `async`-muotoon**

`resolveAndNext` on nyt `async`, joten kutsujien on odotettava sitä. Muuta nämä neljä (rivit ~300, ~361, ~378, ~386, ~393) — vain `async` ja `await` lisätään, logiikka ei muutu:

```tsx
  /** One-click: keep largest, reject rest, confirm, next */
  async function handleAutoConfirm() {
    if (!group) return
    const rejectIds = members.filter(m => m.image_id !== suggestedBestId).map(m => m.image_id)
    const keepIds = [suggestedBestId]
    await resolveAndNext(keepIds, rejectIds)
  }
```

```tsx
  /** One-click: keep images from this folder, reject rest, confirm, next */
  async function handleKeepFolderConfirm(folder: string) {
    if (!group) return
    const keepIds = members.filter(m => m.image && folderOf(m.image.file_path) === folder).map(m => m.image_id)
    const rejectIds = members.filter(m => m.image && folderOf(m.image.file_path) !== folder).map(m => m.image_id)
    if (keepIds.length === 0 || rejectIds.length === 0) return
    await resolveAndNext(keepIds, rejectIds)
  }
```

```tsx
  async function handleConfirm() {
    if (!group) return
    const rejectIds = Array.from(groupRejected)
    const keepIds = members.map(m => m.image_id).filter(id => !groupRejected.has(id))
    await resolveAndNext(keepIds, rejectIds)
  }
```

```tsx
  /** Reject ALL images in this group */
  async function handleRejectAll() {
    if (!group) return
    const rejectIds = members.map(m => m.image_id)
    await resolveAndNext([], rejectIds)
  }
```

```tsx
  /** Keep ALL images in this group and mark as resolved */
  async function handleKeepAll() {
    if (!group) return
    const keepIds = members.map(m => m.image_id)
    await resolveAndNext(keepIds, [])
  }
```

Näiden JSX-kutsupaikkoja ei tarvitse muuttaa: `onClick={handleRejectAll}` toimii sellaisenaan, koska React ei odota paluuarvoa.

- [ ] **Step 5: Varmista ettei `onDone`-parametriin jäänyt viittauksia**

```bash
cd frontend && grep -n "onDone" src/pages/Duplicates.tsx
```

Expected: ei osumia.

- [ ] **Step 6: Varmista lint ja tyypit**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: tsc puhdas; lint 6 virhettä / 4 varoitusta. Tarkista erityisesti, ettei uusia `no-floating-promises`- tai `require-await`-virheitä ilmestynyt.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Duplicates.tsx frontend/src/i18n/fi.json frontend/src/i18n/en.json
git commit -m "feat: offer undo for every duplicate action that rejects images (#59)"
```

---

### Task 4: Skannerin muutostunnistus (#54, #58)

**Files:**
- Modify: `backend/indexer/orchestrator.py` (`scan()`, rivit ~152-163)
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: ei mitään aiemmasta tehtävästä.
- Produces: ei uusia julkisia nimiä. `scan()` säilyttää signatuurinsa `async def scan(self) -> int`.

Kaksi vikaa samassa haarassa, joten yksi työ.

**#54:** kun tiedoston koko tai mtime muuttuu, rivi palautetaan `pending`-tilaan mutta `file_hash` jää vanhaksi. `process_file_hashes()` valitsee vain rivit joilla `file_hash IS NULL`, joten vanhentunut SHA-256 säilyy ikuisesti. `find_duplicate_groups` niputtaa `file_hash`in perusteella ja merkitsee ryhmän tyypiksi `exact`, ja `bulk_resolve_duplicates` hylkää automaattisesti muut kuin parhaan exact-ryhmästä — eli vanhentunut tiiviste voi tuottaa väärän "tarkka kopio" -parin.

**#58:** tiedosto, joka on merkitty `missing`-tilaan ja ilmestyy takaisin täsmälleen samankokoisena ja samalla mtimellä, ei koskaan palaa `pending`-tilaan eikä kasvata muutoslaskuria. Tällä on väliä 0.4.15:stä lähtien, koska tuplaryhmittelyn ohitussääntö nojaa `scan()`:n muutoslukuun.

- [ ] **Step 1: Kirjoita kaatuvat testit**

Lisää `tests/test_orchestrator.py`:hen. Tiedostossa on jo apurit `_make_jpeg(path)` ja `_make_session_factory(tmp_path)`, ja `Config`, `Image`, `select` on tuotu.

```python
@pytest.mark.asyncio
async def test_scan_clears_stale_hashes_on_changed_file(tmp_path):
    """A changed file must have file_hash and phash cleared so both get recomputed."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()
    jpg = images_dir / "change.jpg"
    _make_jpeg(jpg)

    config = Config(source_dirs=[str(images_dir)], thumbs_dir=str(tmp_path / "thumbs"))
    session_factory = await _make_session_factory(tmp_path)
    orchestrator = IndexerOrchestrator(config, session_factory)

    await orchestrator.scan()

    # Pretend the file was fully indexed, then changed on disk.
    async with session_factory() as session:
        image = (await session.execute(select(Image))).scalars().one()
        image.status = "indexed"
        image.file_hash = "stalehash"
        image.phash = "stalephash"
        await session.commit()

    _make_jpeg(jpg, size=(400, 400))  # different size on disk

    changed = await orchestrator.scan()

    assert changed >= 1
    async with session_factory() as session:
        image = (await session.execute(select(Image))).scalars().one()
        assert image.status == "pending"
        assert image.file_hash is None
        assert image.phash is None


@pytest.mark.asyncio
async def test_scan_revives_a_missing_file_that_reappears_identical(tmp_path):
    """A 'missing' row whose file exists again must be re-queued even if size/mtime match."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()
    jpg = images_dir / "back.jpg"
    _make_jpeg(jpg)

    config = Config(source_dirs=[str(images_dir)], thumbs_dir=str(tmp_path / "thumbs"))
    session_factory = await _make_session_factory(tmp_path)
    orchestrator = IndexerOrchestrator(config, session_factory)

    await orchestrator.scan()

    # The file is on disk and unchanged, but the row says it went missing.
    async with session_factory() as session:
        image = (await session.execute(select(Image))).scalars().one()
        image.status = "missing"
        await session.commit()

    changed = await orchestrator.scan()

    assert changed >= 1
    async with session_factory() as session:
        image = (await session.execute(select(Image))).scalars().one()
        assert image.status == "pending"
```

- [ ] **Step 2: Aja testit ja varmista että ne kaatuvat**

```bash
source .venv/bin/activate
python -m pytest tests/test_orchestrator.py::test_scan_clears_stale_hashes_on_changed_file tests/test_orchestrator.py::test_scan_revives_a_missing_file_that_reappears_identical -v
```

Expected: molemmat FAIL. Ensimmäinen kaatuu `assert image.file_hash is None` -kohtaan (arvo on yhä `"stalehash"`), toinen `assert changed >= 1` -kohtaan (arvo 0, koska koko ja mtime täsmäävät).

- [ ] **Step 3: Toteuta molemmat korjaukset**

`backend/indexer/orchestrator.py`, korvaa muuttuneen tiedoston haara (rivit 152-163) tällä:

```python
                    if existing is not None:
                        # Re-index if size or mtime changed, or if the row says the file
                        # went missing but it is on disk again — a restored file can come
                        # back byte-identical, so size/mtime alone would never notice it.
                        changed_on_disk = (
                            existing.file_size != file_size
                            or existing.file_mtime != file_mtime
                        )
                        if changed_on_disk or existing.status == "missing":
                            existing.file_size = file_size
                            existing.file_mtime = file_mtime
                            if changed_on_disk:
                                # Content may differ, so both fingerprints are now stale.
                                # process_file_hashes() only picks up rows where
                                # file_hash IS NULL, so a stale hash would otherwise
                                # survive forever and could form a false "exact" group.
                                existing.file_hash = None
                                existing.phash = None
                            # Only reset to pending if not a user decision (kept/rejected)
                            if existing.status not in ("kept", "rejected"):
                                existing.status = "pending"
                                existing.error_message = None
                            await session.commit()
                            changed_count += 1
                            logger.debug("scan: marked changed file for re-index: %s", str_path)
```

Huomaa `changed_on_disk`-ehto tiivisteiden nollauksen ympärillä: palannut mutta muuttumaton tiedosto ei tarvitse uudelleenlaskentaa, vain paluun `pending`-tilaan.

- [ ] **Step 4: Aja testit ja varmista että ne menevät läpi**

```bash
source .venv/bin/activate
python -m pytest tests/test_orchestrator.py -v
```

Expected: PASS. Erityisesti aiemmat `test_scan_re_indexes_changed_files` ja `test_run_full_includes_hashing_and_grouping` pysyvät vihreinä.

- [ ] **Step 5: Aja koko backend-sarja**

```bash
source .venv/bin/activate
python -m pytest -q tests/
```

Expected: 119 passed (116 lähtötaso + 1 Task 2:sta + 2 tästä).

- [ ] **Step 6: Commit**

```bash
git add backend/indexer/orchestrator.py tests/test_orchestrator.py
git commit -m "fix: clear stale hashes on change, revive reappearing missing files (#54, #58)"
```

---

### Task 5: Tuplaryhmittelyn pysäytys ja edistyminen (#55)

**Files:**
- Modify: `backend/indexer/orchestrator.py` (`group_duplicates`, rivit ~827-935)
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: ei mitään aiemmasta tehtävästä.
- Produces: ei uusia julkisia nimiä. `group_duplicates()` säilyttää signatuurinsa `async def group_duplicates(self) -> None`.

Molemmat viat näkyvät nyt jokaisella indeksoinnilla, koska 0.4.14 toi ryhmittelyn automaattiseen putkeen.

**Pysäytys:** `group_duplicates()` ei tarkista `_stop_event`iä lainkaan. 0.4.15 siirsi raskaan laskennan säikeeseen, joten Pysäytä-pyyntö saadaan nyt perille — mutta vaihe ajetaan silti loppuun.

**Edistyminen:** `state.total` asetetaan kuvamäärään (~38 000) mutta `state.processed` pysyy nollassa koko vaiheen ja hyppää lopuksi ryhmien määrään (~4 585). Palkki näyttää 0 % koko ajan ja päättyy 12 %:iin.

- [ ] **Step 1: Kirjoita kaatuva testi**

Testi todistaa **molemmat suunnat samalla datalla**. Pelkkä "pysäytyksen jälkeen ei ryhmiä" menisi läpi tyhjästä, jos ryhmittely ei olisi luonut ryhmää muutenkaan — se olisi testi, joka ei voi kaatua.

```python
@pytest.mark.asyncio
async def test_group_duplicates_honours_stop_request(tmp_path):
    """Grouping creates a group for this data, and a stop request prevents exactly that."""
    from backend.db.models import DuplicateGroup

    async def _seed(factory):
        async with factory() as session:
            for i in range(2):
                session.add(
                    Image(
                        file_path=f"/p/dup{i}.jpg", file_name=f"dup{i}.jpg", file_size=10,
                        file_mtime=float(i), status="indexed", phash="f" * 16,
                    )
                )
            await session.commit()

    async def _group_count(factory):
        async with factory() as session:
            return len((await session.execute(select(DuplicateGroup))).scalars().all())

    config = Config(
        source_dirs=[str(tmp_path / "photos")],
        thumbs_dir=str(tmp_path / "thumbs"),
    )

    # _make_session_factory writes <dir>/test.db but does not create <dir> itself.
    control_dir = tmp_path / "control"
    stopped_dir = tmp_path / "stopped"
    control_dir.mkdir()
    stopped_dir.mkdir()

    # Control: without a stop request, this data DOES produce a group. Without this
    # half, the assertion below would pass vacuously.
    control_factory = await _make_session_factory(control_dir)
    await _seed(control_factory)
    await IndexerOrchestrator(config, control_factory).group_duplicates()
    assert await _group_count(control_factory) == 1

    # Same data, stop requested first: nothing is written.
    stopped_factory = await _make_session_factory(stopped_dir)
    await _seed(stopped_factory)
    stopped = IndexerOrchestrator(config, stopped_factory)
    stopped.request_stop()
    await stopped.group_duplicates()
    assert await _group_count(stopped_factory) == 0
```

`_make_session_factory` ottaa hakemistopolun ja luo sinne `test.db`:n, joten kaksi eri alihakemistoa antaa kaksi erillistä kantaa. Luo hakemistot ensin, jos apuri ei tee sitä itse — tarkista `_make_session_factory`:n toteutus tiedoston alusta.

Jos control-puolisko ei tuota ryhmää, älä heikennä väitettä — selvitä mitä `find_duplicate_groups` odottaa `phash`-kentältä ja korjaa testidata sen mukaiseksi. Ryhmittymätön control tarkoittaa, ettei testi todista mitään.

- [ ] **Step 2: Aja testi ja varmista että se kaatuu**

```bash
source .venv/bin/activate
python -m pytest tests/test_orchestrator.py::test_group_duplicates_honours_stop_request -v
```

Expected: FAIL — ryhmä luodaan, koska `group_duplicates()` ei katso `_stop_event`iä.

- [ ] **Step 3: Lisää pysäytystarkistukset**

`backend/indexer/orchestrator.py`, `group_duplicates()`. Lisää tarkistus kolmeen kohtaan, kunkin kalliin vaiheen väliin. Käytä samaa muotoa kuin muualla tiedostossa.

Heti `self._notify()`-rivin jälkeen metodin alussa:

```python
        if self._stop_event.is_set():
            logger.info("group_duplicates: stop requested, skipping")
            return
```

Heti kuvien latauksen jälkeen, ennen `find_duplicate_groups`-kutsua:

```python
        if self._stop_event.is_set():
            logger.info("group_duplicates: stop requested before grouping")
            return
```

Heti `find_duplicate_groups`-kutsun palattua, ennen kirjoitusvaihetta:

```python
        if self._stop_event.is_set():
            logger.info("group_duplicates: stop requested, discarding results")
            return
```

Viimeinen on tärkein: se estää sen, että pysäytyspyyntö jättäisi tietokannan puolittain kirjoitettuun tilaan.

- [ ] **Step 4: Korjaa edistymisen raportointi**

Samassa metodissa. Ongelma on, että `state.total` tarkoittaa kuvia mutta `state.processed` päätyy tarkoittamaan ryhmiä. Yhtenäistä ne kirjoitusvaiheeseen: kun ryhmät on löydetty, aseta `state.total` ryhmien määräksi ja kasvata `state.processed`ia ryhmä kerrallaan.

Juuri ennen silmukkaa, joka luo uudet ryhmät (`for group_data in groups:`), aseta:

```python
            self.state.total = len(groups)
            self.state.processed = 0
            self._notify()
```

ja silmukan rungon loppuun, jokaisen luodun ryhmän jälkeen:

```python
                self.state.processed += 1
                if self.state.processed % 50 == 0:
                    self._notify()
```

`% 50` pitää WebSocket-liikenteen kohtuullisena ~4 500 ryhmällä. Lisää lopuksi silmukan jälkeen `self._notify()`, jotta viimeinen erä näkyy.

Älä poista alun `state.total = len(all_images)` -asetusta: se antaa mielekkään luvun latausvaiheen ajaksi, ennen kuin ryhmien määrä on tiedossa.

- [ ] **Step 5: Aja testit**

```bash
source .venv/bin/activate
python -m pytest tests/test_orchestrator.py -v
```

Expected: PASS. Erityisesti `test_run_full_includes_hashing_and_grouping` ja `test_run_full_stop_skips_grouping_and_eviction` pysyvät vihreinä.

- [ ] **Step 6: Aja koko backend-sarja**

```bash
source .venv/bin/activate
python -m pytest -q tests/
```

Expected: 120 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/indexer/orchestrator.py tests/test_orchestrator.py
git commit -m "fix: make duplicate grouping stoppable and report real progress (#55)"
```

---

### Task 6: Versionnosto, changelog ja julkaisu

**Files:**
- Modify: `pyproject.toml` (`version`)
- Modify: `CHANGELOG.md`
- Build: `frontend/dist/`

**Interfaces:**
- Consumes: Task 1-5:n muutokset.
- Produces: julkaisukelpoinen 0.4.18.

- [ ] **Step 1: Nosta versio**

`pyproject.toml`: `version = "0.4.17"` → `version = "0.4.18"`.

- [ ] **Step 2: Kirjoita changelog-merkintä**

Lisää `CHANGELOG.md`:hen uusimmaksi versiolohkoksi, `## [0.4.17]`:n yläpuolelle. **Englanniksi**, samalla tyylillä kuin aiemmat: lihavoitu aloitusfraasi, ajatusviiva, selittävä proosa, tiedostoviittaukset backtickeissä lopussa. Kirjoita merkintä sen mukaan, mitä oikeasti muuttui — mainitse issue-numerot.

Katettavat asiat:
- Peruutus jokaiselle tuplatoiminnolle, joka hylkää kuvia, ei enää vain kuvasarjojen pikavalinnalle (#59)
- 404 vanhentuneelle ryhmälle hiljaisen onnistumisen sijaan (#52)
- Asetukset astuvat voimaan heti tallennuksen jälkeen (#60)
- Vanhentuneiden tiivisteiden nollaus muuttuneelta tiedostolta ja palanneen tiedoston huomaaminen (#54, #58)
- Tuplaryhmittelyn pysäytettävyys ja todellinen edistyminen (#55)
- Suomenkielisten merkkijonojen ääkköset ja burst-termin yhtenäistäminen (#56)

- [ ] **Step 3: Rakenna frontend uudelleen**

```bash
cd frontend && npm run build
```

Expected: build menee läpi, `frontend/dist/`-tiedostot saavat uuden aikaleiman.

- [ ] **Step 4: Aja koko sarja**

```bash
source .venv/bin/activate
python -m pytest -q tests/
```

Expected: 120 passed.

- [ ] **Step 5: Commit ja push**

`frontend/dist` on gitignoressa eikä sitä committoida.

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "chore: release v0.4.18"
git push
```

- [ ] **Step 6: Käynnistä tuotantopalvelu uudelleen**

Palvelu ajaa vanhaa koodia kunnes se käynnistetään uudelleen. `get_version()` on `lru_cache`tetty, joten pelkkä tiedostojen vaihtuminen ei riitä.

```bash
launchctl kickstart -k gui/$(id -u)/com.fotoxi.serve
sleep 8
curl -s http://localhost:8001/api/version
```

Expected: `{"version":"0.4.18"}`.

Huom: PWA:n service worker cachettaa vanhan buildin, joten selain näyttää vanhaa käyttöliittymää kunnes se päivitetään pari kertaa tai service worker poistetaan rekisteristä. Tämä ei ole julkaisuvirhe — varmista tarvittaessa suoraan buildista:

```bash
grep -c "images_rejected" frontend/dist/assets/*.js
```

- [ ] **Step 7: Sulje issuet**

```bash
gh issue close 52 54 55 56 58 59 60 --comment "Fixed in v0.4.18."
```

---

## Muistiinpanot seuraavalle työlle (ei tässä laajuudessa)

- **#51** — `find_duplicate_groups` piikittää ~8 GB `checked_phash`-memon takia (`grouping/duplicates.py:109-119`). Mittaus ilman memoa: 13,9 s / 0,06 GB. Vaatii oman työn, joka todistaa ryhmittelytuloksen pysyvän identtisenä.
- **#53** — indeksointiputki on määritelty kolmessa paikassa. `_process_only` (`routes.py:1061`) evictaa yhä pilvitiedostot ilman hashausta, ja virheiden uudelleenyritys käyttää sitä.
- **#61** — `kept_at` / `rejected_at` eivät palaudu peruutuksessa.
- **#57** — `source_dirs` voi sisältää saman kansion kahdesti, mikä tuottaa React-avainvirheitä ja saa skannerin kävelemään saman puun kahdesti.
