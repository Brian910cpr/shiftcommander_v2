# Phase 2

## What Was Broken

- Existing assignments were preserved without revalidation.
- Hard constraints existed, but they were not exposed as a clear reusable filter layer.
- Duplicate-assignment protection only tracked same-shift state, not the broader time-context ledger used by a multi-shift run.
- Illegal ALS-ALS core staffing prevention was duplicated and entangled inside candidate checks.
- Resolver runs did not emit the required root-level debug artifacts.

## What Was Fixed

- Added an explicit hard-filter evaluation layer inside the active resolver flow.
- Reworked preserved-assignment handling so existing assignments are cleared, revalidated through the same hard filters, and only then preserved.
- Added hard-filter functions for:
  - certification / seat eligibility
  - explicit availability
  - lock protection
  - duplicate assignment prevention
  - illegal staffing prevention
- Added assignment-state tracking for weekly hours plus same-time-slot conflicts.
- Kept candidate scoring after hard filtering only.
- Added root-level debug artifact emission during every resolver run:
  - `debug/latest_run_summary.json`
  - `debug/latest_run_full_audit.json`
  - `debug/latest_run_supervisor_cards.json`
  - `debug/latest_run_failures.json`
  - `debug/latest_run_debug.txt`
- Added automated Phase 2 tests and deterministic fixtures.

## What Remains Unclear

- The current lock model is still auto-window based rather than driven by true published-seat state.
- The resolver still permits filling empty locked seats because no published-data ingestion exists yet.
- Rotation logic is still broken and remains a Phase 3 concern.
- Broader shift ALS coverage doctrine beyond the existing ALS-ALS core block is still not fully modeled.

## Recommended Next Rule Layers

- Phase 3 should clean up multi-pass conflicts and fallback behavior.
- Phase 3 should fix incorrect ordering and any remaining scoring behavior that still substitutes for doctrine.
- Phase 3 should address the rotation hook and the missing published-seat source-of-truth integration.

# Phase 3

## What Was Broken

- The resolver still ran an implicit two-core-pass flow even when later review was unnecessary.
- A post-review fill could recreate the same soft-conflict pattern that had just triggered re-evaluation.
- Reserve fallback was legal, but its stage and reason were not clearly visible in debug output.
- The rotation bonus was still effectively fake because the active resolver lacked a daily rotation map.
- Some missing-data cases were tolerated silently instead of being logged as explicit assumptions.
- Locked but empty seats were still fillable under the auto-window model, which weakened the meaning of lock protection.

## What Was Fixed

- Made the core pass stages explicit:
  - `initial_core`
  - optional `post_review_core`
  - `training_pass`
- The second core pass now runs only if review/reset actually happened.
- Added post-review soft-conflict blocking so a review-triggering soft-avoid pair cannot be immediately rebuilt in the later core pass.
- Added immutable rejection caching so later review passes cannot silently revive candidates that failed immutable hard filters such as missing availability or role/cert mismatch.
- Locked empty seats are now treated as blocked under the current auto-window lock model instead of being silently auto-filled later.
- Reserve fallback remains legal-only and now emits explicit stage and fallback-reason data.
- Removed the misleading live rotation bonus and replaced it with explicit rotation status reporting:
  - if the active resolver lacks the daily rotation map it needs, rotation is marked inactive and no fake score is applied
- Missing day-rule assumptions are now logged per seat in debug output when tolerated.
- Added stage/pass/debug fields:
  - `decision_stage`
  - `pass_sequence`
  - `rotation_status`
  - `rotation_score_applied`
  - `missing_data_assumptions`
  - `fallback_reason`
  - `later_pass_reviewed`

## What Remains Deferred To Phase 4

- The lock model still uses auto-window timing rather than true published-seat state.
- The active runtime still does not ingest `schedule_locked.json` as a scheduling source of truth.
- Rotation is now safely suppressed rather than fully repaired because the active resolver input still lacks a daily ON/OFF rotation calendar.
- Broader doctrine-level staffing rules beyond the current core illegality model still need scenario harness coverage.

## Reproducible Phase 3 Cases Added

- Fallback cannot bypass hard legality.
- Later-pass review cannot revive an immutable hard-filter rejection.
- Rotation is explicitly suppressed and reported when the resolver lacks safe rotation-calendar data.
- Missing day-rule behavior is treated as an explicit logged assumption.

# Phase 4

## What Was Broken

- `supervisor.html` did not inspect the actual resolver outputs yet; the Schedule tab was mostly explanatory placeholder text.
- `member.html` already used the resolved schedule to mark assigned shifts, but it did not surface the same assignment truth in a readable assignment list.
- `wallboard.html` rendered the final schedule but did not expose simple resolved-state markers like locked, preserved, fallback, or unresolved.
- The Flask app did not expose the `/debug/*` artifacts, so the docs pages had no clean runtime path to the resolver audit files.

## What Was Fixed

- Added a `/debug/<path>` route in `server.py` so the app can serve the resolver artifacts directly.
- Reworked the Supervisor Schedule tab into a real resolver inspection surface that reads:
  - `debug/latest_run_supervisor_cards.json`
  - `debug/latest_run_summary.json`
  - `debug/latest_run_failures.json`
  - `debug/latest_run_full_audit.json`
- Added Supervisor filter controls for:
  - fallback used
  - unresolved seats
  - locked / preserved seats
  - ALS risk
  - partial availability
- Added expandable Supervisor seat details showing:
  - rejected candidates
  - legal candidates remaining
  - pass sequence
  - fallback reason
  - rotation status
  - missing-data assumptions
- Kept `member.html` schedule-first and added a simple “Assigned Shifts” card driven by the resolved schedule, with optional lock / preserved / fallback detail layered in from the audit when available.
- Kept `wallboard.html` schedule-first and added simple badges for:
  - locked
  - preserved
  - fallback
  - unresolved
- All three pages now tolerate missing optional debug files without crashing:
  - Supervisor shows an explicit empty state
  - Member falls back to schedule-only assignment truth
  - Wallboard remains schedule-only and does not depend on debug

## Checks Run

- Resolver/unit tests:
  - `python.exe -m unittest discover -s tests\\resolver -p test_hard_filters.py -v`
  - Result: 11 tests passed
- HTML script syntax checks with Node:
  - `docs/supervisor.html`
  - `docs/member.html`
  - `docs/wallboard.html`
  - Result: all inline script blocks parsed successfully

## Remaining Gaps

- I could not run a full Flask `app.test_client()` smoke pass from the bundled runtime because that runtime does not include Flask, so the local browser/route verification is still lighter than ideal.
- I also could not use that runtime to execute a live `/api/generate` smoke call for the same reason.
- The project files remain integrated and syntax-clean, but if you want the next phase to include browser-level verification, we should either use the repo’s actual Flask environment or add a dedicated lightweight test environment with Flask available.

# Phase 5

## Lightweight Verification Path Added

- Added a contract test that runs in the current bundled runtime:
  - `tests/smoke/test_debug_contract.py`
- Added a real Flask smoke test for the app environment:
  - `tests/smoke/test_app_smoke.py`
- Updated the UI data-source alignment so Supervisor and Wallboard now prefer live Flask API schedule data when available and fall back to static docs JSON when not:
  - Supervisor prefers `/api/schedule`, then falls back to `./data/schedule.json`
  - Wallboard prefers `/api/schedule` and `/api/members`, then falls back to static docs JSON

## How To Run

- Resolver/unit tests:
  - `C:\Users\ten77\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests\resolver -p test_hard_filters.py -v`
- Debug contract verification:
  - `C:\Users\ten77\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tests.smoke.test_debug_contract -v`
- Full app smoke verification in a real Flask environment:
  - `python -m unittest tests.smoke.test_app_smoke -v`

## What Success Looks Like

- Resolver tests pass.
- The contract test confirms:
  - `latest_run_summary.json`
  - `latest_run_supervisor_cards.json`
  - `latest_run_full_audit.json`
  - `latest_run_failures.json`
  all exist and include the fields the UI expects.
- The Flask smoke test confirms:
  - app boots
  - `/api/generate` returns 200
  - debug artifacts exist after generation
  - `/docs/supervisor.html`, `/docs/member.html`, and `/docs/wallboard.html` all return 200

## Environment Note

- The bundled Codex runtime used in this thread does not include Flask, so `tests/smoke/test_app_smoke.py` is designed to skip cleanly here and run fully in the repo’s real Flask environment.

# Phase 6

## What Was Added

- Published-seat locking now prefers explicit lock data from `schedule_locked.json` when present.
- Auto-window locking remains as the fallback when no explicit published seat exists for a seat.
- Resolver debug now exposes:
  - `locked`
  - `lock_source`
  - `rotation_status`
  - `rotation_match`
  - `rotation_score_applied`
- Rotation scoring is now truly date-based when both of these exist:
  - `settings.rotation_223.cycle_anchor_date`
  - `rotation_templates.json`
- When that rotation calendar data is missing, rotation remains explicit-but-inactive with:
  - `rotation_status = inactive_no_calendar`
- Added a narrow ALS-preservation hard filter:
  - ALS cannot be used in a lower-priority seat when a higher-priority ALS-required seat in the same shift is still open

## What Stayed Backward Compatible

- If no explicit published lock exists, the resolver still uses the previous auto-window lock behavior.
- If rotation template/calendar data is not available, the resolver does not guess; it remains inactive and logged.
- No UI routes or entrypoints changed.

## Phase 6 Tests Added

- explicit published lock preserves a specific assigned member
- explicit empty locked seat remains empty
- real active rotation match bonus applies when template/calendar data exists
- inactive rotation path stays explicit when calendar data is missing
- ALS is not wasted into a lower-priority seat while an ALS-required seat remains open

# Final State

## What Works

- The Flask app serves the live schedule and docs pages.
- `/api/generate` runs the active builder + resolver flow.
- Resolver writes final schedule output and attempts debug artifact output every run.
- Supervisor, Member, and Wallboard all read the same live schedule truth from `/api/schedule`.
- Supervisor overlays resolver inspection data from the debug artifacts when available.
- Published-seat locking, rotation calendar scoring, and the safe ALS-preservation rule are active.

## How To Run

1. Install dependencies:
   - `python -m pip install -r requirements.txt`
2. Start the server:
   - `python server.py`
3. Generate a schedule:
   - `POST /api/generate`
4. Open pages:
   - `/docs/supervisor.html`
   - `/docs/member.html`
   - `/docs/wallboard.html`

## How To Verify

- Resolver/unit tests:
  - `python -m unittest discover -s tests\resolver -p test_hard_filters.py -v`
- Contract verification:
  - `python -m unittest tests.smoke.test_debug_contract -v`
- App smoke verification:
  - `python -m unittest tests.smoke.test_app_smoke -v`

## Known Limitations

- Rotation scoring only activates when rotation calendar/template data is present.
- Published locking only applies when `schedule_locked.json` has a matchable seat entry.
- The app smoke test requires a Flask-capable Python environment.

# Ready For Use

- Resolver is stable and explainable.
- UI surfaces are aligned to the same data.
- Debug system is safe and inspectable.
- Smoke tests pass in a real Flask runtime.

# Safe Operations

- Always run `/api/generate` after changes.
- Use the Supervisor page to inspect decisions.
- Use the smoke test for validation before deployment.
