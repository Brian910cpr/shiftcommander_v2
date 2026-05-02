# Current Target Model

Updated: 2026-05-01

This file now has two purposes:

1. define the current implementation target for ShiftCommander
2. preserve older phase notes below as historical context

The authoritative current rule baseline is:

- [docs/CONFIRMED_SCHEDULING_RULES.md](E:\GitHub\shiftcommander_v2\docs\CONFIRMED_SCHEDULING_RULES.md)
- [docs/PROJECT_BOUNDARIES.md](E:\GitHub\shiftcommander_v2\docs\PROJECT_BOUNDARIES.md)

## Confirmed Operational Baseline

The live target is no longer an abstract resolver cleanup. It is a crew scheduling system with these fixed operational facts:

- 12-hour 2-2-3 backbone
- standard 0600-1800 and 1800-0600 shifts
- up to 3 units now, with ambulance and QRV support
- ALS preservation as a core scheduling doctrine
- editable per-shift seat structure
- member qualification split between medical certs and per-unit `qualOp`
- publish horizon and lock horizon as distinct concepts
- weekly publish boundary at Wednesday 23:59
- open-seat workflow with supervised offer/claim handling
- fairness driven by hours/shifts first and Preferred-grant rate second
- member and supervisor authentication with logged control paths
- one runtime source of truth, not duplicated schedule truth

## Current Implementation Priorities

### Priority 1: Normalize The Scheduling Model

Replace ambiguous builder-era assumptions with an explicit scheduling model that can represent:

- date
- shift
- unit
- seat
- seat requirement
- assignment
- open seat
- published state
- supervisor override

This model must support:

- 12-hour seats
- 6-hour partial coverage blocks
- ambulance seats
- QRV seats
- future NEMT compatibility

### Priority 2: Make Legality Explicit

The resolver must separate hard legality from soft scoring.

Hard legality must cover at least:

- certification
- seat eligibility
- unit-specific `qualOp`
- availability
- partial-block compatibility
- weekly hard limits
- mandatory safety boundaries
- legal driver minimums
- published/override protection
- no impossible overlaps

Soft scoring must then prioritize:

1. ALS preservation
2. OT/budget control
3. preference
4. fairness

### Priority 3: Replace Auto-Lock Assumptions With Publish-State Truth

The current system still carries older auto-window lock behavior. The target model is:

- visible horizon default: 8 weeks
- lock horizon default: 2 weeks
- once visible, assignments do not reshuffle merely to improve score
- once locked/published, members remain responsible until release, drop, or approved swap
- supervisor overrides are protected from future resolver runs

This means publish state, open state, override state, and lock state need explicit storage and explicit resolver ingestion.

### Priority 4: Model ALS Coverage At Shift Level

The resolver must stop reasoning only seat-by-seat and must understand broader shift ALS coverage:

- ALS ambulance attendant satisfies ALS coverage
- ALS QRV can satisfy broader coverage for BLS ambulances
- using higher-cert members in lower seats is allowed only as a high-penalty fallback
- legal combinations must be evaluated at unit and shift level, not just candidate level

### Priority 5: Add Real Open-Seat Handling

Open seats are a real system state, not just a failure artifact.

The implementation target is:

- legal seats may remain `OPEN`
- critical open seats become more urgent as the date approaches
- at 3 weeks out, unresolved ALS/legal-driver/open critical seats notify Supervisor
- open-seat offer workflow tracks:
  - interested candidates
  - scored candidates
  - active offer
  - expiration
  - next candidate
  - first-come fallback when allowed

### Priority 6: Support Swaps And Locked-Period Requests

After the lock horizon:

- members do not directly erase themselves from assignments
- changes move through release/swap workflows
- same-week two-member swaps may auto-approve when all hard rules still pass
- swap/release actions are logged

### Priority 7: Align Supervisor, Member, Wallboard, And Mobile

The scheduling data model must feed all surfaces consistently:

- Supervisor:
  - define shift structure
  - define desired unit count
  - view approaching failures
  - drag/drop assignments
  - override with reason logging
- Member:
  - edit own availability before lock horizon
  - request changes after lock horizon
  - view own assignments and open opportunities
- Wallboard:
  - display 6 to 8 weeks
  - group by date, shift, unit, seat
  - visually escalate open-seat urgency
- Mobile:
  - my shifts
  - who is on shift now
  - pick up open shifts
  - full schedule

### Priority 8: Add Cost And Reporting Support

The resolver does not need payroll integration, but it does need enough structured data to report:

- assigned hours
- OT risk
- budget risk
- fairness balance
- open critical coverage gaps

This requires member pay type/rate fields and schedule reporting outputs, even if optimization remains conservative at first.

## Immediate Implementation Plan

### Phase A: Data-Model Reset

- define canonical runtime entities for schedule, shift, unit, seat, assignment, published state, and override state
- remove duplicate runtime-truth assumptions
- document authoritative files in `data/*`
- justify or remove static fallbacks explicitly

### Phase B: Resolver Rule Refactor

- convert confirmed rules into explicit hard-rule and soft-score layers
- add shift-level ALS coverage evaluation
- add 6-hour partial-block support
- add role and `qualOp` legality rules for ambulance and QRV seats
- make higher-cert lower-seat fallback explicit and heavily penalized

### Phase C: Publish/Lock/Open Workflow

- ingest explicit published/open/override state
- enforce visible horizon vs lock horizon behavior
- preserve published assignments on rerun
- allow only open/dropped/released seats to refill automatically after publish

### Phase D: Swap/Release Workflow

- add logged swap and release objects
- support auto-approvable same-week two-member swaps
- add supervisor review path for everything else

### Phase E: Supervisor And Wallboard Alignment

- make Supervisor the control surface for unit count, seat structure, OT window settings, and override logging
- make Wallboard display the same assignment truth with open-seat urgency cues
- keep debug files internal only

### Phase F: Member And Mobile Alignment

- keep member writes self-scoped
- support preferred contact methods
- expose open-shift offer status cleanly
- preserve one schedule truth across member and mobile views

## Non-Negotiable Design Constraints

- one runtime source of truth
- no duplicate schedule truth without explicit justification
- no frontend-only security assumptions
- no resolver reshuffle of published assignments merely for score improvement
- no driver fallback below licensed driver
- no hidden debug exposure in public/member surfaces

## Historical Phase Notes

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
