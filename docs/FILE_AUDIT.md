# File Audit

Audit date: 2026-04-29  
Repo: `E:\GitHub\shiftcommander_v2`

## Project Boundary

This audit is for ShiftCommander only.

- `schedule` means EMS/fire crew schedule
- `shift` means a duty period
- `unit` or `truck` means apparatus/ambulance
- `seat` means a required staffing position on a unit
- `member` means responder/employee/volunteer
- `assignment` means a member placed into a seat
- `availability` means member availability to work
- `wallboard` means schedule display

910CPR, Enrollware, lander, course, class-session, HOVN, or CPR terminology does not apply to this repo and should not be used to justify cleanup decisions here.

## Scope

This audit covers project-owned files in the repo and intentionally excludes `.venv`, `.git`, and `__pycache__` noise. The goal is to map:

- live runtime inputs used by `server.py` and `engine/resolver.py`
- files referenced by `docs/*.html`
- files written by the running system
- duplicate and backup files
- files with no detected references

`Referenced by` is based on direct imports, route usage, fetches, CLI defaults, and text/grep cross-checks. A file with no detected textual reference is not automatically dead, but it is called out explicitly.

## Classification Key

- `KEEP`: live runtime input, live UI, active code, or active test/support file
- `CANDIDATE`: duplicate, fallback, stale mirror, or file that may still serve a narrow purpose but should be consolidated
- `DEAD`: not referenced by live code or clearly obsolete/broken
- `UNKNOWN`: intent exists but live usage is unclear

## Expected Runtime-Created Files

These files are written by the system but were not present in the scanned tree at audit time.

| File path | Purpose | Referenced by | Last modified | Classification |
|---|---|---|---|---|
| `data/auth_users.json` | Session auth/password store | `server.py:load_auth_users()`, `save_auth_users()` | Not present in scan | `KEEP` |
| `data/supervisor_state.json` | Supervisor publish/open/drop state | `server.py:load_supervisor_state()`, `save_supervisor_state()` | Not present in scan | `KEEP` |
| `debug/latest_run_summary.json` | Resolver debug summary | `engine/resolver.py:resolve()` write path, `tests/smoke/test_debug_contract.py` | Not present in scan | `KEEP` |
| `debug/latest_run_full_audit.json` | Resolver audit detail | `engine/resolver.py:resolve()` write path | Not present in scan | `KEEP` |
| `debug/latest_run_supervisor_cards.json` | Resolver supervisor card output | `engine/resolver.py:resolve()` write path | Not present in scan | `KEEP` |
| `debug/latest_run_failures.json` | Resolver failures report | `engine/resolver.py:resolve()` write path | Not present in scan | `KEEP` |
| `debug/latest_run_debug.txt` | Resolver text debug dump | `engine/resolver.py:resolve()` write path | Not present in scan | `KEEP` |
| `data/availability.backup.YYYYMMDD-HHMMSS.json` | Timestamped backup made before clear-future wipe | `server.py:backup_json_file()` | Pattern only | `KEEP` |

## Core App And Runtime Data

| File path | Purpose | Referenced by | Last modified | Classification |
|---|---|---|---|---|
| `server.py` | Main Flask app, API, auth, schedule writes | App entrypoint; tests hit routes directly | Recent, 2026-04-21/22 | `KEEP` |
| `engine/__init__.py` | Package marker | Python package import | 2026-04-07 | `KEEP` |
| `engine/resolver.py` | Core schedule resolver, validation, debug artifact writer | `server.py:/api/generate`, CLI entrypoint | Recent, 2026-04-21 | `KEEP` |
| `engine/shift_builder.py` | Shift demand builder | `server.py:/api/build_shifts`, imported directly | 2026-04-07 | `KEEP` |
| `engine/rotation_engine.py` | Rotation/fairness helper | Imported by `engine/resolver.py` | 2026-04-07 | `KEEP` |
| `engine/rules.py` | Rule definitions/supporting policy logic | Engine support module | 2026-04-07 | `KEEP` |
| `engine/data_access.py` | Data helper module | Engine support module | 2026-04-07 | `KEEP` |
| `engine/schedule_board_filter.py` | CLI board filter writer | Standalone utility; writes filtered board JSON | 2026-04-07 | `KEEP` |
| `requirements.txt` | Python dependency list | Environment/bootstrap | 2026-04-07 | `KEEP` |

## Primary Live Data Under `data/`

| File path | Purpose | Referenced by | Last modified | Classification |
|---|---|---|---|---|
| `data/members.json` | Primary member roster | `server.py`, `engine/resolver.py`, `docs/wallboard.html` fallback via API/member data model | 2026-04-07 | `KEEP` |
| `data/availability.json` | Primary availability source | `server.py`, `engine/resolver.py`, `engine/shift_builder.py` | 2026-04-07 | `KEEP` |
| `data/settings.json` | Resolver/build settings | `server.py`, `engine/resolver.py` | 2026-04-07 | `KEEP` |
| `data/shifts.json` | Generated shift demand | `server.py`, `engine/resolver.py`, tests | 2026-04-21 14:02 | `KEEP` |
| `data/schedule.json` | Primary resolved schedule output | `server.py`, `docs/wallboard.html`, tests | 2026-04-21 14:02 | `KEEP` |
| `data/schedule_locked.json` | Lock input for resolver/publish state | `server.py`, `engine/resolver.py` | 2026-04-07 | `KEEP` |
| `data/rotation_templates.json` | Rotation template definitions | `server.py`, rotation features | 2026-04-07 | `KEEP` |
| `data/inferred_preferences.json` | Preference side-data; declared by server but no active write/read path found beyond constant | `server.py` constant only | 2026-04-07 | `UNKNOWN` |
| `data/schedule_board.json` | Filtered/board-style schedule artifact | Not referenced by live app routes; likely output from `engine/schedule_board_filter.py` | 2026-04-07 | `CANDIDATE` |
| `data/swap_requests.json` | Swap-request dataset | No live route or engine usage found | 2026-04-07 | `UNKNOWN` |
| `data/2025-08.normalized.json` | Normalized month snapshot | No live app usage found; likely legacy normalization output | 2026-04-07 | `CANDIDATE` |
| `data/2025-09.normalized.json` | Normalized month snapshot | No live app usage found | 2026-04-07 | `CANDIDATE` |
| `data/2025-10.normalized.json` | Normalized month snapshot | No live app usage found | 2026-04-07 | `CANDIDATE` |
| `data/2025-11.normalized.json` | Normalized month snapshot | No live app usage found | 2026-04-07 | `CANDIDATE` |
| `data/2025-12.normalized.json` | Normalized month snapshot | No live app usage found | 2026-04-07 | `CANDIDATE` |
| `data/2026-01.normalized.json` | Normalized month snapshot | No live app usage found | 2026-04-07 | `CANDIDATE` |
| `data/2026-02.normalized.json` | Normalized month snapshot | No live app usage found | 2026-04-07 | `CANDIDATE` |

## Duplicate, Backup, And Conflicting Data Files

| File path | Purpose | Referenced by | Last modified | Classification |
|---|---|---|---|---|
| `schedule.json` | Root-level schedule copy outside `data/` | No live code usage found | 2026-04-07 | `DEAD` |
| `data/schedule - Copy.json` | Manual duplicate schedule copy | No references found | 2026-04-07 | `DEAD` |
| `data/schedule_WORKS_backup.json` | Backup schedule snapshot | No references found | 2026-04-07 | `CANDIDATE` |
| `data/availability_BACKUP.json` | Backup availability snapshot | No references found | 2026-04-07 | `CANDIDATE` |
| `data/members_BACKUP.json` | Backup members snapshot | No references found | 2026-04-07 | `CANDIDATE` |
| `data/shifts_BACKUP.json` | Backup shifts snapshot | No references found | 2026-04-07 | `CANDIDATE` |

## Public Docs And UI Files

| File path | Purpose | Referenced by | Last modified | Classification |
|---|---|---|---|---|
| `docs/index.html` | Redirect/entry page | Public docs root entrypoint | 2026-04-07 | `KEEP` |
| `docs/supervisor.html` | Supervisor UI | Served by `server.py`, tested route target | 2026-04-22 23:53 | `KEEP` |
| `docs/member.html` | Member self-service UI | Served by `server.py`, tested route target | 2026-04-22 23:48 | `KEEP` |
| `docs/wallboard.html` | Wallboard UI | Served by `server.py`, tested route target | 2026-04-22 23:31 | `KEEP` |
| `docs/CNAME` | Static hosting/domain metadata | Static host deployment support | 2026-04-07 | `KEEP` |
| `docs/memb_er.html` | Older member-page typo clone with local JSON assumptions and broad edit paths | No live references; fetches old `/api/members` and `/api/availability` flows | 2026-04-07 15:25 | `DEAD` |
| `docs/wallboar-d.html` | Older wallboard-page typo clone | No live references; points at stale `/data/schedule.json` pattern | 2026-04-07 | `DEAD` |
| `docs/shared.js` | Generic fetch helper | No live references found from current HTML | 2026-04-07 | `DEAD` |
| `docs/styles.css` | Older shared stylesheet | No live references found from current HTML | 2026-04-07 | `DEAD` |

## `docs/data/` Mirrors And Fallbacks

| File path | Purpose | Referenced by | Last modified | Classification |
|---|---|---|---|---|
| `docs/data/schedule.json` | Static schedule mirror/fallback | `docs/wallboard.html:SCHEDULE_URLS` fallback | 2026-04-07 | `CANDIDATE` |
| `docs/data/members.json` | Static members mirror/fallback | `docs/wallboard.html:MEMBERS_URLS` fallback; old `docs/memb_er.html` | 2026-04-07 | `CANDIDATE` |
| `docs/data/availability.json` | Static availability mirror | Old `docs/memb_er.html` only | 2026-04-07 | `CANDIDATE` |
| `docs/data/settings.json` | Static settings mirror | Old/stale local-data path only | 2026-04-07 | `CANDIDATE` |
| `docs/data/shifts.json` | Static shifts mirror | Old/stale local-data path only | 2026-04-07 | `CANDIDATE` |
| `docs/data/schedule_locked.json` | Static lock mirror | Old/stale local-data path only | 2026-04-07 | `CANDIDATE` |
| `docs/data/schedule_board.json` | Static board mirror | No live references found | 2026-04-07 | `DEAD` |
| `docs/data/org_settings.json` | Duplicate settings variant | No live references found | 2026-04-07 | `DEAD` |
| `docs/data/overrides.json` | Override placeholder | No live references found; current resolver does not load it | 2026-04-07 | `DEAD` |
| `docs/data/assignments_history.json` | Empty/placeholder history file | No live references found | 2026-04-07 | `DEAD` |

## Scripts And Tests

| File path | Purpose | Referenced by | Last modified | Classification |
|---|---|---|---|---|
| `scripts/build_draft_schedule.py` | Legacy builder script | `RULES.md` says it imports a non-existent `build_schedule` from `server.py`; no live usage found | 2026-04-07 | `DEAD` |
| `tests/smoke/test_app_smoke.py` | Smoke test for app routes and file writes | Test suite | 2026-04-07 | `KEEP` |
| `tests/smoke/test_debug_contract.py` | Debug artifact contract test | Test suite | 2026-04-07 | `CANDIDATE` |
| `tests/resolver/test_hard_filters.py` | Resolver logic tests | Test suite | 2026-04-07 | `KEEP` |
| `tests/fixtures/resolver_base.json` | Resolver test fixture | `tests/resolver/test_hard_filters.py` | 2026-04-07 | `KEEP` |
| `tests/fixtures/resolver_multipass_review.json` | Resolver test fixture | Resolver tests | 2026-04-07 | `KEEP` |
| `tests/fixtures/resolver_preserved_assignment.json` | Resolver test fixture | Resolver tests | 2026-04-07 | `KEEP` |
| `tests/fixtures/resolver_reserve_fallback.json` | Resolver test fixture | Resolver tests | 2026-04-07 | `KEEP` |

## Reference Docs And Notes

| File path | Purpose | Referenced by | Last modified | Classification |
|---|---|---|---|---|
| `FLOW.md` | Data-flow notes | Human reference only | 2026-04-07 | `CANDIDATE` |
| `RULES.md` | Rules/process notes | Human reference only; contains stale claims | 2026-04-07 | `CANDIDATE` |
| `DATA_CONTRACT.md` | Data-contract notes | Human reference only | 2026-04-07 | `CANDIDATE` |
| `IMPLEMENTATION_SUMMARY.md` | Historical implementation notes | Human reference only | 2026-04-07 | `CANDIDATE` |
| `CONFLICTS.md` | Historical conflict notes | Human reference only | 2026-04-07 | `CANDIDATE` |
| `structure.txt` | Snapshot of older repo structure | Human reference only; likely stale | 2026-04-07 | `CANDIDATE` |

## Files With No Detected Live References

These are the clearest cleanup targets because no active code path or current HTML references them.

- `schedule.json`
- `data/schedule - Copy.json`
- `docs/memb_er.html`
- `docs/wallboar-d.html`
- `docs/shared.js`
- `docs/styles.css`
- `docs/data/schedule_board.json`
- `docs/data/org_settings.json`
- `docs/data/overrides.json`
- `docs/data/assignments_history.json`
- `scripts/build_draft_schedule.py`

## Key Duplicate And Conflict Findings

### 1. Multiple schedule sources can disagree

There are at least three schedule payloads that look authoritative:

- `data/schedule.json` — live server output
- `docs/data/schedule.json` — static mirror/fallback
- `schedule.json` — root-level stray copy

This is the biggest stale-data bug risk in the repo. A removed or changed future schedule or assignment can disappear from one file and still appear in another.

### 2. `docs/data/*` mirrors are not consistently maintained

`docs/data/availability.json`, `members.json`, `settings.json`, `shifts.json`, and `schedule_locked.json` duplicate live `data/*` files, but the current primary UI paths mostly call APIs instead. That means the mirrors can quietly drift and still be read by fallback code or old pages.

### 3. Two typo-clone HTML pages preserve older behavior

- `docs/memb_er.html`
- `docs/wallboar-d.html`

These pages are dead from a navigation standpoint, but they still embody older client assumptions and older data sources. If someone bookmarks them or if a static host exposes them, they can surface stale member data, stale wallboard data, or obsolete edit behavior.

### 4. Runtime-created files are missing from source control scan

`data/auth_users.json`, `data/supervisor_state.json`, and resolver debug outputs are expected by live code even though they were absent during the scan. This is fine operationally, but it means a fresh repo checkout does not fully represent the app's live state.

### 5. Tests and docs are partially stale

`tests/smoke/test_debug_contract.py` still expects `docs/supervisor.html` to reference direct debug JSON endpoints. The current supervisor direction has moved away from depending on those debug paths. That makes this test a possible false alarm generator.

### 6. Legacy normalized month files appear orphaned

The `data/YYYY-MM.normalized.json` files were not found in any live server or resolver load path. They look like normalization artifacts from an older availability pipeline and should not sit beside live source-of-truth data without clear ownership.

## Stale Files Most Likely To Cause Real Bugs

- `docs/data/schedule.json`
  - Old static fallback can keep stale assignments visible even after `data/schedule.json` changes.
- `schedule.json`
  - Looks authoritative by name, but no live code uses it.
- `docs/memb_er.html`
  - Older member page can encourage the wrong request patterns and stale member-data reads.
- `docs/wallboar-d.html`
  - Older wallboard can render outdated schedule copies.
- `tests/smoke/test_debug_contract.py`
  - Can force maintenance toward obsolete debug assumptions.

## Proposed Cleanup Plan

No files should be deleted until approved. The safe sequence is to archive first, then remove only after a successful verification pass.

### Move To `data/archive`

- `data/availability_BACKUP.json`
- `data/members_BACKUP.json`
- `data/shifts_BACKUP.json`
- `data/schedule_WORKS_backup.json`
- `data/schedule - Copy.json`
- `data/2025-08.normalized.json`
- `data/2025-09.normalized.json`
- `data/2025-10.normalized.json`
- `data/2025-11.normalized.json`
- `data/2025-12.normalized.json`
- `data/2026-01.normalized.json`
- `data/2026-02.normalized.json`

Reason: these are snapshots, experiments, or older normalization outputs, not clean live inputs.

### Delete After Approval

- `schedule.json`
- `docs/memb_er.html`
- `docs/wallboar-d.html`
- `docs/shared.js`
- `docs/styles.css`
- `docs/data/schedule_board.json`
- `docs/data/org_settings.json`
- `docs/data/overrides.json`
- `docs/data/assignments_history.json`
- `scripts/build_draft_schedule.py`

Reason: no live references found, and several actively preserve obsolete behavior.

### Consolidate

1. Pick one authoritative runtime data tree: `data/*`.
2. Either remove `docs/data/*` entirely or regenerate it from `data/*` in one explicit build step.
3. Remove the root-level `schedule.json` so there is no second schedule file pretending to be primary.
4. Decide whether `data/schedule_board.json` is still needed.
   - If yes: document its producer and consumer.
   - If no: archive then remove it and its static mirror.
5. Decide whether `data/inferred_preferences.json` and `data/swap_requests.json` are real product features or abandoned experiments.
   - If real: add routes/tests/docs.
   - If not: archive and remove.

### Validation Before Any Cleanup

Before deleting anything:

1. Start `server.py` and verify:
   - `/docs/supervisor.html`
   - `/docs/member.html`
   - `/docs/wallboard.html`
2. Run smoke tests and resolver tests.
3. Confirm wallboard still renders when API is available.
4. Confirm no remaining route or HTML file references the typo-clone pages or old `docs/data/*` mirrors.
5. If static fallback is still desired, replace ad hoc mirrors with one documented export step.

## Bottom Line

The repo's main structural risk is not the resolver code. It is the number of duplicate schedule/data copies and stale fallback pages sitting next to live files with nearly identical names. That is exactly the kind of setup that makes stale schedules, stale assignments, stale availability, or old auth behavior appear to "come back."

The safest cleanup path is:

1. declare `data/*` as the runtime source of truth
2. archive backups and normalized artifacts
3. remove dead typo-clone pages and dead support files
4. either formalize or remove `docs/data/*` mirrors
5. update stale tests/docs after the file cleanup is approved
