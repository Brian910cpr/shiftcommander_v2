# ShiftCommander Local Resolver Validation Handoff

Date: 2026-07-19

## Goal

Inspect the local ShiftCommander resolver, run its tests, attempt a real schedule resolution from available local data, and make the smallest fixes needed without touching unrelated 910CPR code.

## Primary Result

The supervisor resolver previously received zero shifts when `data/schedule.json` and `data/shifts.json` were absent, even though the published fallback `docs/data/schedule.json` contained 170 shifts. `server.py` now falls back to that published local schedule for resolver input, matching the read-only schedule API behavior.

The corrected server preview path dry-ran 170 shifts from 2026-05-18 through 2026-08-10. No schedule was saved or published.

## Primary Audit Output

Exact contents of `debug/latest_run_summary.json` after the server preview:

```json
{
  "filled_attendant_seats": 41,
  "filled_driver_seats": 93,
  "open_attendant_seats": 129,
  "open_driver_seats": 77,
  "duty_crew_seats_filled": 36,
  "duty_crew_seats_open": 0,
  "rotation_authorized_seats_filled": 0,
  "expected_rotation_ot_hours": 0.0,
  "additional_ot_hours": 216.0,
  "ot_avoided_by_emt_fallback": 0,
  "shifts_needing_supervisor_review": 0,
  "members_rejected_due_to_do_not": 68,
  "members_skipped_due_to_unset": 0,
  "members_rejected_due_to_ot_restriction": 1692,
  "members_receiving_open_shift_notice_eligibility": 1423,
  "adr_zipper_enabled": false,
  "adr_zipper_simulation_only": true,
  "adr_zipper_24_compression_candidates": 0,
  "seat_count": 340,
  "filled_seats": 67,
  "unfilled_seats": 273
}
```

The rule-based summary counts structural driver coverage differently from the raw assigned-seat audit, which explains why its filled-driver total does not equal the audit's raw `filled_seats` count. This discrepancy should be made explicit in future supervisor reporting.

## MVP Fixture Result

`scripts/run_slot_schedule_mvp.py` completed:

- 6 slots evaluated
- 4 assigned
- 3 exception records
- one `judgment` assignment with alternatives
- one `override_needed` unfilled driver slot
- one hard-blocked event slot

The generator preserved human approval by returning supervisor actions and did not mutate its input.

## Tests

- `tests/resolver/test_hard_filters.py`: 15 passed
- `tests/resolver/test_rule_based_resolver.py`: 41 passed
- `tests/resolver/test_operational_stabilization.py`: 5 passed
- `tests/resolver/test_slot_schedule_generator.py`: 7 passed
- `tests/smoke/test_app_smoke.py`: 31 passed
- Python syntax validation passed for the changed server, runner, resolver modules, and tests.

Total directly reported passing tests: 99.

## Changed Files

- `server.py`: resolver input now falls back to `docs/data/schedule.json` after live and raw shift sources are absent.
- `requirements.txt`: declares `tzdata` on Windows so `America/New_York` server startup works locally.
- `tests/smoke/test_app_smoke.py`: adds resolver fallback coverage and makes availability-write test dates future-safe.
- `tests/resolver/test_hard_filters.py`: makes a missing-Friday-rule test future-safe.
- `scripts/run_slot_schedule_mvp.py`: makes direct execution resolve the repository import path.
- `data/audit/chatgpt_handoff_resolver_local_validation.md`: this handoff.

Pre-existing uncommitted files were preserved:

- `data-seed/slot_schedule_mvp_week.json`
- `engine/slot_schedule_generator.py`
- `scripts/run_slot_schedule_mvp.py`
- `tests/resolver/test_slot_schedule_generator.py`
- `data/google_calendar_june_2026_mirror.json`

The calendar mirror was already dirty before this work. Server smoke execution refreshed it from the configured calendar feed, so it remains intentionally unstaged and must be reviewed separately before any commit.

## Missing Inputs / Blockers

- No current authoritative `data/schedule.json` or `data/shifts.json`; the resolver now uses the published fallback locally.
- No schedule beyond 2026-08-10 in the published fallback, so the referenced August board cannot be fully reconstructed or validated from repository data.
- Availability is largely generated/inferred from historical patterns, not confirmed current member submissions.
- The dry run left many seats open because candidates were rejected by availability and overtime rules. It did not force illegal assignments.
- The current rule-based resolver exposes open reasons and audit files, but it reports zero `shifts_needing_supervisor_review` even with open required seats. That supervisor exception count needs a policy/UI correction.
- No credentials are required for local tests or dry runs. Credentials are only needed for live calendar refresh, durable cloud state, notifications, deployment, or publishing remote changes.

## Next Implementation Steps

1. Designate and persist one authoritative current shift-demand file, including the full August horizon.
2. Import/confirm current August availability rather than relying on historical inference.
3. Make every open required seat appear in the supervisor exception count/queue, with filter reason counts.
4. Reconcile structural-driver summary metrics with raw assigned-seat metrics.
5. Run a supervisor-approved dry run for one Thursday-Wednesday week, review every exception, then publish only after explicit approval.

## Deployment / Git Status

- Persisted locally: yes
- Changed in repo: yes
- Validated locally: yes
- Dry-run tested: yes
- Deployed: no
- Committed: no
- Pushed: no

## 2026-07-19 Rollout Reality Update

The rollout model was changed after operational clarification:

- Display horizon is fixed through `2026-08-31`, then returns to an 8-week rolling view.
- Required AM/PM demand is always built for the 84-day planning horizon, even when nobody has submitted availability.
- Blank availability no longer permits an FT baseline auto-assignment.
- Overtime and base-hour calculations reset on the Thursday-Wednesday operational workweek instead of accumulating across the whole planning horizon.
- Member availability API submissions have no far-future cutoff; a regression test verifies a 2031 submission.
- The member UI offers views through five years and explains that availability is independent of the displayed schedule horizon.
- All inferred/generated future availability was backed up and reset to blank. Backup: `data/availability.backup.20260719-234212.json`.
- Reset result: 8,343 future dates cleared across both supported data shapes, 21,526 exact future values cleared, and 258 pattern values cleared. Verification found zero remaining declared future intents.
- Blank-availability dry-run proof: 170 required shifts built from 2026-07-19 through 2026-10-11, producing 267 open seats and 3,570 member notice-eligibility records instead of hiding the shifts.
- Resolver and server validation after the change: 42 rule-based resolver tests, 5 stabilization tests, and 33 server smoke tests passed.
- Frontend production build remains blocked by the existing local Node/PostCSS dependency runtime (`Unexpected token '<'` while loading a PostCSS plugin); source syntax changes were not identified as the cause.
