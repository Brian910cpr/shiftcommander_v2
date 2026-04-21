# Resolver Flow Audit

Audit target: `E:\GitHub\shiftcommander_v2`

Status: Phase 1 only. No code changes made.

## Active Execution Path

### Web/API flow

1. `server.py:363` `/api/generate` runs `generate_schedule()`.
2. `generate_schedule()` calls `run_shift_builder()`.
3. `run_shift_builder()` imports `engine.shift_builder.build_shift_skeletons`.
4. `build_shift_skeletons()` generates shift skeletons from:
   - active members
   - settings day rules
   - availability payload
5. `run_shift_builder()` writes the result to `data/shifts.json`.
6. `generate_schedule()` then calls `run_resolver()`.
7. `run_resolver()` imports `engine.resolver.resolve`.
8. `run_resolver()` loads:
   - `members.json`
   - `shifts.json`
   - `settings.json`
   - `availability.json`
9. `run_resolver()` writes resolver output to `data/schedule.json`.

### CLI flow inside resolver

1. `engine/resolver.py:1557` `main()` loads JSON inputs from CLI args.
2. `main()` calls `resolve(data)`.
3. `main()` writes output JSON and prints build summary.

## Shift Builder Flow

### Function chain

- `build_shift_skeletons()`
  - `get_active_member_ids()`
  - `any_member_available_for_shift()`
  - `get_day_rule()`
  - `seats_for_pattern()`

### Behavior

- `FACT`: the builder only creates shifts where at least one active member is marked `preferred` or `available`.
- `FACT`: `ALS` day-rule shifts receive only `DRIVER` and `ATTENDANT` seats.
- `FACT`: non-`ALS` day-rule shifts receive `DRIVER`, `ATTENDANT`, and `3RD_RIDER`.
- `FACT`: builder output does not preload published assignments, locked seats, overrides, or legality metadata.

## Resolver Flow

### Context build

`resolve(data)` starts with `build_context(data)`.

`build_context()` creates:
- merged policy from `DEFAULT_POLICY` and top-level matching settings keys
- usable member list and member index
- weekly-hours accumulator
- restricted pairing set from settings
- empty assigned-this-shift set
- deep-copied shifts
- availability index
- build timestamp
- training assignment tracker

### Important implementation detail

- `FACT`: `get_policy()` only copies keys from the top level of `settings` if they match `DEFAULT_POLICY`.
- `FACT`: the current repo settings place most business rules under `settings.rules`, `settings.rotation`, and `settings.rotation_223`.
- `INFERENCE`: much of the intended configuration is not actually consumed by the active resolver policy merge.

## Per-Shift Execution Order

For each shift in `ctx["shifts"]`, `resolve()` executes:

1. `initialize_shift_state(shift, ctx)`
2. `preserve_existing_assignments(shift, ctx)`
3. `run_shift_passes(shift, ctx)`
4. `re_evaluate_unlocked_shift_if_needed(shift, ctx)`
5. `ctx["assigned_this_shift"] = set(get_current_assigned_member_ids(shift))`
6. `run_shift_passes(shift, ctx)` again
7. `ctx["assigned_this_shift"] = set(get_current_assigned_member_ids(shift))`
8. `run_training_third_seat_pass(shift, ctx)`

## Shift Initialization

`initialize_shift_state()`:
- computes lock state with `compute_lock_status()`
- writes shift resolver metadata
- stamps every seat with lock metadata
- initializes `candidate_audit`
- computes `als_required`
- defaults non-third seats to active
- defaults `3RD_RIDER` seats to inactive hidden training seats

### Locking behavior

- `FACT`: `compute_lock_status()` marks a shift locked if its date is within `(visible_weeks + lock_buffer_weeks) * 7` days of today.
- `FACT`: no published schedule file or override file is consulted here.

## Existing Assignment Preservation

`preserve_existing_assignments()`:
- accumulates weekly hours for already-assigned seats
- sets `assigned_this_shift` from those assignments
- appends notes preserving locked or existing assignments

### Important consequence

- `FACT`: preserved assignments are not revalidated through `member_can_fill_seat()`.

## Core Pass Pipeline

`run_shift_passes()` does:

1. split members into `normal_pool` and `reserve_pool`
2. iterate seats in order
3. skip `3RD_RIDER`
4. skip inactive seats
5. skip already-assigned seats
6. choose best candidate from normal pool
7. if none and reserve relief is allowed, choose best candidate from reserve pool
8. if still none, mark seat open

### Candidate selection order

`choose_best_candidate()` does:

1. initialize `candidate_audit`
2. for each candidate in pool:
   - run `member_can_fill_seat()`
   - if rejected, append ineligible audit row
   - if accepted, run `score_member_for_seat()`
   - append eligible audit row with score breakdown
3. if no candidates survive, build `failure_summary`
4. sort by `(-score, member_id)`
5. return the top candidate

### Commit

`commit_assignment()`:
- adds weekly hours
- adds member id to `assigned_this_shift`
- writes seat assignment fields
- marks reserve support usage
- records fill pass

## Unpublished Re-Evaluation Flow

`re_evaluate_unlocked_shift_if_needed()`:

1. exits immediately if shift is locked
2. exits if `allow_unpublished_recalc` is false
3. checks `shift_has_soft_avoid_conflict()`
4. checks `shift_has_restricted_conflict()`
5. if neither conflict exists, exits
6. otherwise clears all unlocked assignments via `clear_unlocked_assignments()`
7. preserves only locked-seat member ids in `assigned_this_shift`
8. appends notes explaining re-evaluation trigger

### Important consequence

- `FACT`: the resolver performs at least two core fill waves for unlocked shifts.
- `FACT`: this re-evaluation is triggered only by restricted-pair and soft-avoid conflicts.
- `INFERENCE`: other illegal or undesirable crew combinations are not re-evaluated at shift level.

## Training Pass Flow

`run_training_third_seat_pass()`:

1. calls `activate_training_seats()`
2. builds training pool from probationary members
3. iterates only active `3RD_RIDER` seats
4. chooses best trainee
5. commits trainee or hides seat again if none wins

## Output Flow

`build_output()` returns:
- `build.generated_at`
- `build.lock_window_days`
- `build.summary`
- `shifts`

`summarize_fill_stats()` computes:
- fill rates
- reserve fills
- training fills
- assignment-status counts
- truck-type counts like `als_als_trucks`, `als_bls_trucks`, `bls_bls_trucks`

## Hidden or Indirect Paths

- `FACT`: `schedule_locked.json` exists and contains normalized locked published assignments, but `run_resolver()` does not load it.
- `FACT`: `overrides.json` exists as a supervisor UI concept, but `run_resolver()` does not load it.
- `FACT`: supervisor UI contains published/controlled/planning phase logic, but active resolver lock logic does not reference that model.
- `FACT`: `rotation_engine.py` exists but is not imported by `engine/resolver.py`.

## Fact / Inference Summary

### Fact

- Active resolver path is `server.py -> engine.shift_builder -> engine.resolver`.
- Resolver has two core passes with intermediate re-evaluation.
- Existing assignments are preserved before candidate filtering.
- Locking is auto-window based.
- Published schedule and overrides are not part of the active resolver input.

### Inference

- The current active runtime is only partially integrated with the richer supervisor/published-seat model present in the UI.
- Resolver behavior likely diverged from intended operational workflow as UI concepts grew faster than backend enforcement.
