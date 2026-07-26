# Sarjakuvien pikavalinta ja peruutus — toteutussuunnitelma

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nostaa "Säilytä suositeltu" sarjakuvaryhmien näkyväksi pikavalinnaksi ja tehdä siitä turvallinen peruutettavan toast-ilmoituksen avulla.

**Architecture:** Uusi `POST /duplicates/{group_id}/unresolve` purkaa ryhmän ratkaisun: nollaa jäsenten `user_choice`n ja palauttaa kuvien statukset kutsujan antamiin arvoihin. Kutsuja lähettää entiset statukset, koska tietokanta ei niitä säilytä — sama kuvio kuin Haku-sivun undossa (`Search.tsx:693-705`). Frontendissä sarjakuvaryhmä saa kaksi rinnakkaista päänappia, ja hylkäävä pikavalinta näyttää toastin Kumoa-toiminnolla. Uusi asetus `dup_confirm_quick_actions` (oletus pois) lisää halutessaan vahvistusdialogin.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2.0 async / pytest (`asyncio_mode = "auto"`), React 19 + TypeScript + TanStack Query + Tailwind 4.

## Global Constraints

- Trunk-based: committoi suoraan `main`iin. Ei feature-brancheja, ei PR:iä.
- Venv on aktivoitava ennen jokaista Python-komentoa: `source .venv/bin/activate`.
- Versionnosto `pyproject.toml`:iin ja merkintä `CHANGELOG.md`:hen tässä työssä: **0.4.15 → 0.4.16**. (Suunnitelma `2026-07-26-indexing-consolidation.md` on toteutettu ja julkaistu 0.4.14:nä, ja sen jälkikorjaus vei numeron 0.4.15. Käytä 0.4.16:ta kauttaaltaan, myös alla olevassa CHANGELOG-esimerkissä.)
- `CHANGELOG.md` kirjoitetaan **englanniksi** (kuten aiemmat merkinnät). Käyttöliittymätekstit tulevat i18n-avaimista.
- `frontend/dist` rakennetaan uudelleen (`cd frontend && npm run build`) frontend-muutosten jälkeen.
- UI:ta käytetään puhelimella Tailscalen yli — muuttunut UI tarkistetaan ~390px leveydellä.
- `t(key)` **ei tue interpolaatiota** (`frontend/src/i18n/useTranslation.ts`). Lukuarvot yhdistetään template-literaalilla, kuten muualla koodissa (`Duplicates.tsx:649`).
- Rajaus: muutos koskee vain sarjakuvaryhmiä (`isBurst`). Kopioryhmien päänappiin ei kosketa.

---

### Task 1: Backend — ratkaisun purku

**Files:**
- Modify: `backend/db/queries.py` (uusi funktio `resolve_duplicate_group`-funktion jälkeen, ~rivi 286)
- Modify: `backend/api/routes.py:14-20` (importit), `backend/api/routes.py:911-923` (uusi endpoint `resolve_duplicate`-endpointin jälkeen)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `DuplicateGroup`, `DuplicateGroupMember`, `Image` — jo importoitu `queries.py`:ssä rivillä 10. `HTTPException` ja `BaseModel` ovat jo käytössä `routes.py`:ssä.
- Produces:
  - `async def unresolve_duplicate_group(session: AsyncSession, group_id: int, statuses: dict[int, str]) -> bool` — palauttaa `False`, jos ryhmää ei ole, muuten `True`.
  - `POST /api/duplicates/{group_id}/unresolve`, runko `{"statuses": {"<image_id>": "<status>"}}`, vastaus `{"status": "unresolved"}` tai 404.

- [ ] **Step 1: Write the failing test**

Lisää `tests/test_api.py`:hen `test_bulk_resolve_duplicates_dry_run`-testin jälkeen:

```python
@pytest.mark.asyncio
async def test_unresolve_duplicate_group(app, client):
    """POST /api/duplicates/{id}/unresolve restores prior statuses and clears choices."""
    from sqlalchemy import select
    from backend.db.models import Image, DuplicateGroup, DuplicateGroupMember

    factory = app.state.session_factory
    async with factory() as s:
        a = Image(file_path="/p/a.jpg", file_name="a.jpg", file_size=100,
                  file_mtime=1.0, width=1000, height=1000, status="indexed")
        b = Image(file_path="/p/b.jpg", file_name="b.jpg", file_size=100,
                  file_mtime=2.0, width=2000, height=2000, status="indexed")
        s.add_all([a, b])
        await s.flush()
        g = DuplicateGroup(match_type="burst")
        s.add(g)
        await s.flush()
        s.add(DuplicateGroupMember(group_id=g.id, image_id=a.id, is_best=False))
        s.add(DuplicateGroupMember(group_id=g.id, image_id=b.id, is_best=True))
        await s.commit()
        group_id, a_id, b_id = g.id, a.id, b.id

    # Resolve: keep b, reject a.
    resp = await client.post(
        f"/api/duplicates/{group_id}/resolve", json={"keep": [b_id], "reject": [a_id]}
    )
    assert resp.status_code == 200

    # Undo it, restoring both to their previous "indexed" status.
    resp = await client.post(
        f"/api/duplicates/{group_id}/unresolve",
        json={"statuses": {str(a_id): "indexed", str(b_id): "indexed"}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "unresolved"

    async with factory() as s:
        rows = (await s.execute(select(Image).where(Image.id.in_([a_id, b_id])))).scalars().all()
        assert {r.status for r in rows} == {"indexed"}
        assert all(r.rejected_at is None and r.kept_at is None for r in rows)

        members = (
            await s.execute(
                select(DuplicateGroupMember).where(DuplicateGroupMember.group_id == group_id)
            )
        ).scalars().all()
        assert all(m.user_choice is None for m in members)


@pytest.mark.asyncio
async def test_unresolve_unknown_group_returns_404(client):
    """POST /api/duplicates/{id}/unresolve returns 404 for a group that doesn't exist."""
    resp = await client.post("/api/duplicates/99999/unresolve", json={"statuses": {}})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate
python -m pytest tests/test_api.py::test_unresolve_duplicate_group tests/test_api.py::test_unresolve_unknown_group_returns_404 -v
```

Expected: FAIL, molemmat saavat 404:n reitin puuttumisen takia (ensimmäinen odottaa 200:aa).

- [ ] **Step 3: Add the query helper**

`backend/db/queries.py`, lisää `resolve_duplicate_group`-funktion perään:

```python
async def unresolve_duplicate_group(
    session: AsyncSession,
    group_id: int,
    statuses: dict[int, str],
) -> bool:
    """Undo a resolution: clear user choices and restore prior image statuses.

    The database does not keep the pre-resolution status, so the caller passes
    it back in ``statuses`` (image id -> status). Images missing from the map
    keep whatever status they currently have; their ``user_choice`` is cleared
    regardless, so the group shows up as unresolved again.

    Returns ``False`` if no such group exists.
    """
    group = await session.get(DuplicateGroup, group_id)
    if group is None:
        return False

    member_result = await session.execute(
        select(DuplicateGroupMember).where(DuplicateGroupMember.group_id == group_id)
    )
    members = list(member_result.scalars().all())

    image_result = await session.execute(
        select(Image).where(Image.id.in_([m.image_id for m in members]))
    )
    images = {img.id: img for img in image_result.scalars().all()}

    _now = datetime.datetime.utcnow()
    for member in members:
        member.user_choice = None
        previous = statuses.get(member.image_id)
        image = images.get(member.image_id)
        if previous is None or image is None:
            continue
        image.status = previous
        image.status_changed_at = _now
        if previous != "kept":
            image.kept_at = None
        if previous != "rejected":
            image.rejected_at = None

    await session.commit()
    return True
```

- [ ] **Step 4: Add the endpoint**

`backend/api/routes.py`, lisää `unresolve_duplicate_group` importtilistaan riveillä 14-20 (aakkosjärjestyksessä `search_images`-rivin jälkeen ei osu — sijoita `retry_errored`in jälkeen, ennen `search_images`ia):

```python
from backend.db.queries import (
    bulk_resolve_duplicates,
    errors_summary,
    resolve_duplicate_group,
    retry_errored,
    search_images,
    unresolve_duplicate_group,
)
```

Lisää sitten `resolve_duplicate`-endpointin perään (rivin 923 jälkeen):

```python
class UnresolveBody(BaseModel):
    statuses: Dict[int, str] = {}


@router.post("/duplicates/{group_id}/unresolve")
async def unresolve_duplicate(
    request: Request, group_id: int, body: UnresolveBody
) -> Dict[str, Any]:
    """Undo a duplicate-group resolution, restoring the given prior statuses."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        found = await unresolve_duplicate_group(
            session=session, group_id=group_id, statuses=body.statuses
        )
    if not found:
        raise HTTPException(status_code=404, detail="Duplicate group not found")
    return {"status": "unresolved"}
```

Pydantic muuntaa JSON-objektin merkkijonoavaimet `int`eiksi `Dict[int, str]`-tyypin perusteella, joten frontend voi lähettää ne sellaisenaan.

- [ ] **Step 5: Run tests to verify they pass**

```bash
source .venv/bin/activate
python -m pytest tests/test_api.py -v
```

Expected: PASS, myös aiemmat API-testit vihreinä.

- [ ] **Step 6: Commit**

```bash
git add backend/db/queries.py backend/api/routes.py tests/test_api.py
git commit -m "feat: add duplicate group unresolve endpoint for undo"
```

---

### Task 2: Asetus `dup_confirm_quick_actions`

**Files:**
- Modify: `backend/config.py` (kentät, `auto_process_on_start`-rivin jälkeen)
- Modify: `backend/api/routes.py:1326-1341` (`SettingsUpdate`), `backend/api/routes.py:1437-1442` (`persist_keys`)
- Modify: `frontend/src/api.ts:94-103` (`AppSettings`)
- Modify: `frontend/src/pages/Settings.tsx:19-30` (lomakkeen alustus), `frontend/src/pages/Settings.tsx:112-128` (uusi valintaruutu perään)
- Modify: `frontend/src/i18n/fi.json`, `frontend/src/i18n/en.json`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 1:n endpoint ei liity tähän; tämä on itsenäinen.
- Produces: `Config.dup_confirm_quick_actions: bool` (oletus `False`), näkyy `GET /api/settings`-vastauksessa ja on asetettavissa `PUT /api/settings`illa. Frontendissä `AppSettings.dup_confirm_quick_actions: boolean`.

- [ ] **Step 1: Write the failing test**

Lisää `tests/test_api.py`:hen:

```python
@pytest.mark.asyncio
async def test_dup_confirm_quick_actions_setting_roundtrip(client):
    """The duplicate quick-action confirm flag defaults off and can be toggled."""
    resp = await client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["dup_confirm_quick_actions"] is False

    resp = await client.put("/api/settings", json={"dup_confirm_quick_actions": True})
    assert resp.status_code == 200

    resp = await client.get("/api/settings")
    assert resp.json()["dup_confirm_quick_actions"] is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate
python -m pytest tests/test_api.py::test_dup_confirm_quick_actions_setting_roundtrip -v
```

Expected: FAIL — `KeyError: 'dup_confirm_quick_actions'`.

- [ ] **Step 3: Add the config field**

`backend/config.py`, lisää `auto_process_on_start: bool = False` -rivin perään:

```python
    dup_confirm_quick_actions: bool = False
```

- [ ] **Step 4: Expose it through the settings API**

`backend/api/routes.py`, `SettingsUpdate`-luokkaan (rivien 1326-1341 lohko), `auto_process_on_start`-rivin perään:

```python
    dup_confirm_quick_actions: Optional[bool] = None
```

ja `persist_keys`-listaan (rivit 1437-1442), jotta asetus säilyy uudelleenkäynnistyksen yli:

```python
    persist_keys = [
        "source_dirs", "ollama_model", "ollama_url", "ai_language",
        "ai_quality_enabled", "phash_threshold", "burst_time_window",
        "ollama_concurrency", "exclude_patterns", "auto_process_on_start", "ui_language",
        "custom_tag_label", "dup_confirm_quick_actions",
    ]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
source .venv/bin/activate
python -m pytest tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Add the field to the frontend settings type**

`frontend/src/api.ts`, `AppSettings`-rajapintaan (rivit 94-103):

```ts
export interface AppSettings {
  ollama_model: string
  ollama_url: string
  ollama_concurrency: number
  ai_language: string
  ai_quality_enabled: boolean
  phash_threshold: number
  custom_tag_label: string
  source_dirs: string[]
  dup_confirm_quick_actions: boolean
}
```

- [ ] **Step 7: Add translation keys**

`frontend/src/i18n/fi.json` (lisää `settings.`-avainten joukkoon):

```json
  "settings.dup_confirm": "Vahvista tuplien pikavalinnat",
  "settings.dup_confirm_desc": "Kysy varmistus ennen kuin sarjakuvan pikavalinta hylkää ruutuja. Ilman tätä hylkäys tapahtuu heti, ja sen voi perua ilmoituksesta.",
```

`frontend/src/i18n/en.json`:

```json
  "settings.dup_confirm": "Confirm duplicate quick actions",
  "settings.dup_confirm_desc": "Ask before a burst quick action rejects frames. Without it the rejection happens immediately and can be undone from the notification.",
```

- [ ] **Step 8: Render the checkbox**

`frontend/src/pages/Settings.tsx`, lisää kenttä lomakkeen alustukseen (rivien 19-30 `setForm({...})`-lohkoon):

```tsx
        dup_confirm_quick_actions: data.dup_confirm_quick_actions,
```

ja uusi valintaruutu heti `quality`-valintaruudun perään (rivin 128 `</div>` jälkeen, saman `<div className="bg-gray-900 …">`-lohkon sisälle):

```tsx
        <div className="flex items-start gap-3">
          <input
            type="checkbox"
            id="dupConfirm"
            checked={form.dup_confirm_quick_actions ?? false}
            onChange={e => setForm(f => ({ ...f, dup_confirm_quick_actions: e.target.checked }))}
            className="mt-0.5 w-4 h-4 rounded border-gray-600 bg-gray-800 accent-blue-500 cursor-pointer"
          />
          <div>
            <label htmlFor="dupConfirm" className="text-sm text-gray-300 cursor-pointer">
              {t('settings.dup_confirm')}
            </label>
            <p className="text-xs text-gray-500 mt-0.5">
              {t('settings.dup_confirm_desc')}
            </p>
          </div>
        </div>
```

- [ ] **Step 9: Verify lint and types**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

Expected: ei uusia virheitä lähtötason 6 virheen / 4 varoituksen päälle.

- [ ] **Step 10: Commit**

```bash
git add backend/config.py backend/api/routes.py tests/test_api.py \
        frontend/src/api.ts frontend/src/pages/Settings.tsx \
        frontend/src/i18n/fi.json frontend/src/i18n/en.json
git commit -m "feat: add dup_confirm_quick_actions setting"
```

---

### Task 3: Sarjakuvien pikavalinta ja undo-toast

**Files:**
- Modify: `frontend/src/api.ts` (uusi `unresolveDuplicateGroup`, sijoita `bulkResolveDuplicates`-funktion lähelle rivin 258 tienoille)
- Modify: `frontend/src/pages/Duplicates.tsx:1-10` (importit), `:280-286` (uusi käsittelijä), `:442-473` (sarjakuvalohko)
- Modify: `frontend/src/i18n/fi.json`, `frontend/src/i18n/en.json`

**Interfaces:**
- Consumes:
  - `POST /api/duplicates/{group_id}/unresolve` Task 1:stä.
  - `AppSettings.dup_confirm_quick_actions` Task 2:sta.
  - `useToast(): { toast, confirm }` `frontend/src/components/Toast.tsx`:stä. `UIProvider` on jo asennettu globaalisti (`App.tsx:189`), joten providereita ei tarvitse lisätä.
  - Olemassa olevat `Duplicates.tsx`:n paikallisnimet: `group`, `members`, `suggestedBestId`, `isBurst`, `resolveAndNext(keepIds, rejectIds)`, `resolveMutation`, `queryClient`, `t`.
- Produces: `export async function unresolveDuplicateGroup(groupId: number, statuses: Record<number, string>): Promise<void>`.

- [ ] **Step 1: Add the API client function**

`frontend/src/api.ts`:

```ts
export async function unresolveDuplicateGroup(
  groupId: number,
  statuses: Record<number, string>,
): Promise<void> {
  const res = await fetch(`${BASE}/duplicates/${groupId}/unresolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ statuses }),
  })
  if (!res.ok) throw new Error(`Unresolve failed: ${res.status}`)
}
```

- [ ] **Step 2: Add translation keys**

`frontend/src/i18n/fi.json`:

```json
  "dup.keep_recommended_short": "Säilytä suositeltu",
  "dup.reject_count": "hylkää",
  "dup.frames_rejected": "ruutua hylätty",
  "dup.confirm_reduce": "Hylätäänkö muut ruudut?",
```

`frontend/src/i18n/en.json`:

```json
  "dup.keep_recommended_short": "Keep recommended",
  "dup.reject_count": "reject",
  "dup.frames_rejected": "frames rejected",
  "dup.confirm_reduce": "Reject the other frames?",
```

**Huom:** `fi.json`:n olemassa olevista `dup.*`-arvoista puuttuvat ääkköset ("Sailyta", "Havita", "Ryhma") — se on erillinen, tämän työn ulkopuolinen vika. Kirjoita **uudet** avaimet oikeaoppisella suomella yllä olevan mukaisesti.

- [ ] **Step 3: Wire up imports and hooks in Duplicates.tsx**

Täydennä `frontend/src/pages/Duplicates.tsx`:n rivin 4 importti ja lisää tarvittavat koukut komponentin alkuun:

```tsx
import { getDuplicates, findDuplicates, bulkResolveDuplicates, thumbUrl,
         unresolveDuplicateGroup, getSettings } from '../api'
import { useToast } from '../components/Toast'
```

Komponentin sisään, muiden koukkujen viereen:

```tsx
  const { toast, confirm } = useToast()
  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: getSettings })
```

- [ ] **Step 4: Add the burst quick-action handler**

Lisää `handleAutoConfirm`-funktion (rivit 281-286) perään:

```tsx
  /** Burst quick action: keep the recommended frame, reject the rest, with undo. */
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

    // The DB does not keep the pre-resolution status, so remember it for undo.
    const groupId = group.id
    const previous: Record<number, string> = {}
    members.forEach(m => {
      if (m.image?.status) previous[m.image_id] = m.image.status
    })

    resolveAndNext([suggestedBestId], rejectIds)

    toast(`${rejectIds.length} ${t('dup.frames_rejected')}`, {
      action: {
        label: t('common.undo'),
        onClick: async () => {
          await unresolveDuplicateGroup(groupId, previous)
          queryClient.invalidateQueries({ queryKey: ['duplicates'] })
        },
      },
    })
  }
```

- [ ] **Step 5: Replace the burst action block**

`frontend/src/pages/Duplicates.tsx`, korvaa sarjakuvahaara (rivit 443-462, `{isBurst ? (` … `)` ennen `: (`) tällä. Pieni "Pienennä parhaaseen" -linkki poistuu, ja tilalle tulee toinen päänappi:

```tsx
      {isBurst ? (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <button
              onClick={handleKeepAll}
              disabled={resolveMutation.isPending}
              className="flex-1 min-w-[9rem] bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white text-sm px-4 py-3 rounded-lg transition-colors font-medium"
            >
              {t('dup.burst_keep_all')} ({members.length})
            </button>
            <button
              onClick={handleBurstReduce}
              disabled={resolveMutation.isPending || members.length < 2}
              className="flex-1 min-w-[9rem] bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-200 text-sm px-4 py-3 rounded-lg border border-gray-600 transition-colors font-medium"
            >
              {t('dup.keep_recommended_short')} ({t('dup.reject_count')} {members.length - 1})
            </button>
          </div>
          <p className="text-xs text-amber-400/80">{t('dup.burst_note')}</p>
        </div>
      ) : (
```

Kopioryhmien haara (`: (` jälkeen, rivit 463-473) jää **muuttumattomana**.

- [ ] **Step 6: Verify lint and types**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

Expected: ei uusia virheitä lähtötason 6 virheen / 4 varoituksen päälle. Tarkista erityisesti, ettei `dup.reduce_to_best`-avaimeen jää viittausta (avain itse voi jäädä JSON-tiedostoihin).

- [ ] **Step 7: Verify in the running app at phone width**

Dev-serverit: backend `python fotoxi.py serve` (portti 8001), frontend `cd frontend && npm run dev -- --host --port 5174`.

Avaa `http://localhost:5174/duplicates` 390px leveydellä ja etsi sarjakuvaryhmä (`match_type: "burst"`). Tarkista:
- Kaksi päänappia näkyvissä: "Säilytä kaikki (sarja) (N)" ja "Säilytä suositeltu (hylkää N−1)".
- Napit pinoutuvat siististi 390px:llä eivätkä leikkaudu oikeasta reunasta.
- "Säilytä suositeltu" hylkää muut ruudut ja siirtyy seuraavaan ryhmään.
- Toast ilmestyy tekstillä "N ruutua hylätty" ja **Kumoa**-painikkeella.
- Kumoa palauttaa ruudut: ryhmä ilmestyy takaisin listaan ja kuvien statukset palautuvat.
- Kun `dup_confirm_quick_actions` laitetaan Asetuksista päälle, pikavalinta kysyy ensin vahvistuksen.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api.ts frontend/src/pages/Duplicates.tsx \
        frontend/src/i18n/fi.json frontend/src/i18n/en.json
git commit -m "ux: prominent keep-recommended quick action for bursts, with undo"
```

---

### Task 4: Versionnosto, changelog ja build

**Files:**
- Modify: `pyproject.toml` (`version`)
- Modify: `CHANGELOG.md`
- Build: `frontend/dist/`

**Interfaces:**
- Consumes: Task 1-3:n muutokset.
- Produces: julkaisukelpoinen 0.4.15 (tai 0.4.14, ks. Global Constraints).

- [ ] **Step 1: Bump version**

`pyproject.toml`: nosta `version` seuraavaan patchiin.

- [ ] **Step 2: Add changelog entry**

Lisää `CHANGELOG.md`:hen ylimmäksi versiolohkoksi, englanniksi:

```markdown
## [0.4.15] - 2026-07-26

### Added
- **"Keep recommended" quick action for bursts** — burst groups used to offer only a big "Keep all" button, with the reduce-to-best action buried in a small underlined link. Bursts now show two side-by-side primary buttons: "Keep all (N)" and "Keep recommended (reject N−1)". (`Duplicates.tsx`)
- **Undo for burst quick actions** — rejecting frames now shows a toast with an **Undo** action. Undo calls the new `POST /api/duplicates/{group_id}/unresolve`, which clears the members' `user_choice` and restores the images' prior statuses. The client sends those statuses back, since the database does not keep them — the same approach the Search page already uses. (`queries.py`, `routes.py`, `api.ts`)
- **`dup_confirm_quick_actions` setting** — off by default. When enabled, a burst quick action asks for confirmation before rejecting frames. (`config.py`, `Settings.tsx`)
```

- [ ] **Step 3: Rebuild the frontend bundle**

```bash
cd frontend && npm run build
```

Expected: build menee läpi, `frontend/dist/`-tiedostot saavat uuden aikaleiman.

- [ ] **Step 4: Run the full suite**

```bash
source .venv/bin/activate
python -m pytest -q tests/
```

Expected: kaikki vihreinä, mukana kolme uutta testiä (`test_unresolve_duplicate_group`, `test_unresolve_unknown_group_returns_404`, `test_dup_confirm_quick_actions_setting_roundtrip`).

- [ ] **Step 5: Commit and push**

`frontend/dist` on gitignoressa (`frontend/.gitignore:11`) eikä sitä committoida — build tehdään paikallisesti, ja palvelu tarjoilee sen työhakemistosta. Lavasta tiedostot nimeltä; älä käytä `git add -A` tai `git add .`, koska repon juuressa lojuu seuraamaton `package-lock.json`, joka ei kuulu versionhallintaan.

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "chore: release v0.4.15"
git push
```

- [ ] **Step 6: Restart the production service**

```bash
launchctl kickstart -k gui/$(id -u)/com.fotoxi.serve
```

Jos palvelu on unloadattu dev-työn ajaksi:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.fotoxi.serve.plist
```

Expected: `curl -s http://localhost:8001/api/version` palauttaa uuden version. PWA:n service worker cachettaa vanhan buildin, joten selain voi vaatia pari uudelleenlatausta.

---

## Muistiinpanot seuraavalle työlle (ei tässä laajuudessa)

- `frontend/src/i18n/fi.json`:n `dup.*`-arvoista puuttuvat ääkköset ("Sailyta suositeltu", "Havita kaikki", "Ryhma"), vaikka 24 muuta riviä samassa tiedostossa käyttää niitä oikein. Näyttää merkistövirheeltä, ei tyylivalinnalta.
- Peruutus palauttaa kuvien statukset ja ryhmän ratkaisemattomaksi, muttei sivutuksen tilaa: jos ryhmä oli sivun viimeinen ja sivutus ehti vaihtua, ryhmä palaa listaan mutta eri kohtaan.
- `resolve_duplicate_group()` ja uusi `unresolve_duplicate_group()` käyttävät `datetime.datetime.utcnow()`-kutsua, joka on deprecoitu Pythonissa. Testiajo tulostaa siitä varoituksia jo nyt useista tiedostoista; siivous kannattaa tehdä kertarysäyksellä koko koodipohjaan.
