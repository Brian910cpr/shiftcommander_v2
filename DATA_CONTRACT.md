# Data Contract

## Resolver Guarantees

- `/api/schedule` returns the final resolved schedule from the active builder + resolver flow.
- Resolver writes these debug artifacts when filesystem access permits:
  - `debug/latest_run_summary.json`
  - `debug/latest_run_supervisor_cards.json`
  - `debug/latest_run_full_audit.json`
  - `debug/latest_run_failures.json`
  - `debug/latest_run_debug.txt`

## UI Expectations

- `supervisor.html`
  - primary truth: `/api/schedule`
  - inspection overlay: `latest_run_supervisor_cards.json`, `latest_run_summary.json`, `latest_run_failures.json`, `latest_run_full_audit.json`
- `member.html`
  - primary truth: `/api/schedule`
- `wallboard.html`
  - primary truth: `/api/schedule`
  - member lookup: `/api/members`

## Strict Rules

- Do not rename resolver or schedule fields without updating every consumer.
- Do not remove fields without coordinated deprecation across resolver, tests, and UI.
- Keep `/api/schedule` as the live source of truth.
