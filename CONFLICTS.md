# Resolver Conflict Audit

Audit target: `E:\GitHub\shiftcommander_v2`

Status: Phase 1 only. No code changes made.

## Summary

The active resolver is not empty. It already has hard filters, scoring, candidate audit output, and multi-pass behavior. The main problem is that core legality, published protection, shift-level doctrine, and preference scoring are mixed unevenly across passes. That allows schedules that are internally consistent with current code but inconsistent with intended operational doctrine.

## Fact vs Inference

- `FACT`: directly observed in code or repo data.
- `INFERENCE`: likely operational consequence from observed code shape.

## Verified Suspected Issues

### 1. Resolver entry point is `engine/resolver.py` via `server.py`

- `FACT`: verified in `server.py` `run_resolver()`.
- Impact:
  - `FACT`: active web generation path uses this resolver.

### 2. No automated tests were found

- `FACT`: no test files were present under the repo.
- Impact:
  - `INFERENCE`: regressions in scoring, legality, and pass interactions are currently easy to introduce silently.

### 3. Rotation exists, but active resolver only uses a weak score hook

- `FACT`: `rotation_engine.py` exists and UI/member data supports `rotation_223_relief`.
- `FACT`: active resolver never imports `rotation_engine.py`.
- `FACT`: active resolver only applies a score bonus in `score_member_for_seat()`.
- Impact:
  - `INFERENCE`: 2-2-3 support is not structurally enforced in the live resolver.

### 4. Rotation matching logic is broken

- `FACT`: `member.rotation.role` is normalized to `A/B/C/D`.
- `FACT`: `get_pattern_key_from_shift()` returns `MON_AM`, `MON_PM`, etc.
- `FACT`: `score_member_for_seat()` compares those incompatible values directly.
- Impact:
  - `FACT`: rotation bonus never fires.
  - `INFERENCE`: scheduler outputs ignore intended home-track preference even when member data is populated.

### 5. Locking is time-window based instead of published-seat based

- `FACT`: `compute_lock_status()` uses only date proximity.
- `FACT`: `run_resolver()` does not load `schedule_locked.json`.
- `FACT`: `run_resolver()` does not load `overrides.json`.
- Impact:
  - `INFERENCE`: actual published or supervisor-locked seats are not protected by the active backend resolver.

### 6. Existing assignments are preserved without revalidation

- `FACT`: `preserve_existing_assignments()` adds weekly hours and notes, but does not call `member_can_fill_seat()`.
- Impact:
  - `INFERENCE`: illegal or stale assignments can survive and shape the rest of the shift as if they were valid.

### 7. Resolver performs multiple passes with hidden re-evaluation

- `FACT`: `resolve()` runs core passes, then `re_evaluate_unlocked_shift_if_needed()`, then core passes again.
- Impact:
  - `INFERENCE`: pass interactions become harder to reason about because state mutates between waves and only some conflict types trigger reset.

### 8. ALS/AEMT normalization exists, but legality and scoring are entangled

- `FACT`: `get_member_cert()` correctly maps `AEMT` and `PARAMEDIC` to `ALS`.
- `FACT`: legality lives partly in hard filters and partly in scores.
- Impact:
  - `INFERENCE`: doctrine-level staffing behavior is only partially guaranteed.

## Conflicts and Rule Breakage

### A. Published-seat protection exists in data/UI but not in active resolver inputs

- `FACT`: `docs/data/schedule_locked.json` contains normalized locked published assignments.
- `FACT`: `docs/supervisor.html` has planning/controlled/published concepts and override locking.
- `FACT`: active resolver ignores both inputs.
- Why this matters:
  - `INFERENCE`: backend recomputation can diverge from what supervisors consider already published or protected.

### B. Shift-level legality is under-modeled

- `FACT`: `seat_requires_als()` only hard-requires ALS on attendant seats for `ALS` day rules.
- `FACT`: no shift-level validator checks “EMT+EMT allowed only if broader shift ALS coverage exists”.
- `FACT`: no broader-coverage context exists in the active scoring or hard-filter path.
- Why this matters:
  - `INFERENCE`: current code can create BLS core trucks on days that doctrine would want constrained by broader ALS coverage.

### C. ALS driver conservation is only a score, not a guardrail

- `FACT`: ALS driver conservation is implemented only as `als_driver_conservation_penalty`.
- `FACT`: full-time minimum bonus is `+100`, larger than the default ALS driver penalty `-75`.
- Why this matters:
  - `INFERENCE`: an ALS member can still beat an EMT driver candidate if other bonuses outweigh the conservation penalty.

### D. Hard and soft ALS-pair logic are duplicated and contradictory

- `FACT`: `member_can_fill_seat()` hard-blocks ALS pairing.
- `FACT`: `score_member_for_seat()` also applies an ALS pair penalty.
- Why this matters:
  - `INFERENCE`: the soft penalty is dead weight in cases already blocked by the hard rule, which obscures intended design and makes future changes risky.

### E. Reserve logic is duplicated across filtering and scoring

- `FACT`: reserve workers are hard-filtered out of the normal pass.
- `FACT`: reserve workers also receive a `-1000` normal-pass score penalty.
- Why this matters:
  - `INFERENCE`: this duplication makes the scoring model harder to trust and signals that the pipeline boundaries are not clean.

### F. Existing assignments can dominate all later logic

- `FACT`: preserved assignments are accepted before any candidate competition.
- `FACT`: re-evaluation only clears unlocked assignments for soft-avoid or restricted-pair triggers.
- Why this matters:
  - `INFERENCE`: if an existing assignment violates certification doctrine, availability doctrine, or broader staffing doctrine, later candidates never get a clean legal contest unless one of those two trigger types happens.

### G. Re-evaluation trigger coverage is too narrow

- `FACT`: re-evaluation only reacts to soft-avoid and restricted-pair conflicts.
- `FACT`: it does not re-evaluate on:
  - missing broader ALS coverage
  - poor driver/attendant resource allocation
  - stale preserved assignments
  - bad full-shift composition
- Why this matters:
  - `INFERENCE`: the second pass fixes only interpersonal conflicts, not resolver-structure conflicts.

### H. Missing-data policy is restrictive for availability, but permissive for other doctrine inputs

- `FACT`: missing availability is a hard reject.
- `FACT`: missing published/locked input is silently ignored because it is not loaded at all.
- `FACT`: missing shift-level legal composition data is effectively treated as “not modeled”.
- Why this matters:
  - `INFERENCE`: the resolver is strict about one data domain and permissive about others, which causes uneven operational safety.

### I. Tie-break logic is simplistic

- `FACT`: candidate sort order is `(-score, member_id)`.
- `FACT`: no explicit tie-break ladder exists for legality-preserving secondary preferences.
- Why this matters:
  - `INFERENCE`: when scores tie, low-member-id ordering can create repeatable but arbitrary winners.

### J. Policy/configuration mismatch

- `FACT`: `get_policy()` only merges top-level settings keys that match `DEFAULT_POLICY`.
- `FACT`: repo settings store important business signals under nested objects like `rules`, `rotation`, and `rotation_223`.
- Why this matters:
  - `INFERENCE`: admins may believe settings are live when they are only partially wired into resolver behavior.

## Why Bad-but-Valid Schedules Happen

### Fact pattern

- `FACT`: candidate-level legality is checked seat-by-seat.
- `FACT`: shift-level doctrine is only partially modeled.
- `FACT`: preserved assignments bypass revalidation.
- `FACT`: re-evaluation trigger coverage is narrow.
- `FACT`: some intended rules exist only as soft score adjustments.
- `FACT`: published/locked operational data is not loaded by the active resolver.

### Result

- `INFERENCE`: the resolver can produce schedules that are valid according to its current seat-level filters and score sort, while still being operationally bad because:
  - a protected published seat was never actually protected
  - a stale assignment stayed in place without legality review
  - ALS was consumed in a driver seat due to scoring tradeoffs
  - 2-2-3 rotation expectations never entered the real competition
  - broader shift ALS coverage doctrine was never checked

## Reproducible Failure Patterns To Prove in Phase 3

These are audit-derived targets, not yet patched.

### Scenario 1: Rotation preference is ignored

- `FACT`: rotation bonus never matches because `A/B/C/D != MON_AM/TUE_PM`.
- Expected Phase 3 proof:
  - two otherwise similar candidates, one on-home rotation and one off-rotation
  - resolver does not reward the intended home-track worker

### Scenario 2: Published protection is ignored by active backend

- `FACT`: active resolver never loads `schedule_locked.json`.
- Expected Phase 3 proof:
  - a seat present in published locked data is not treated as protected by backend generation

### Scenario 3: ALS driver waste can still happen

- `FACT`: ALS driver conservation is only a score penalty.
- Expected Phase 3 proof:
  - an ALS worker with large FT minimum bonus defeats a legal EMT driver candidate

### Scenario 4: Existing invalid assignment persists

- `FACT`: preserved assignments are not revalidated.
- Expected Phase 3 proof:
  - seed an invalid assignment in shift data and show the resolver keeps it

### Scenario 5: EMT+EMT doctrine has no broader-coverage gate

- `FACT`: no broader shift ALS coverage rule exists.
- Expected Phase 3 proof:
  - construct a shift where BLS composition passes current filters but violates intended doctrine

## Recommended Direction for Phase 2 and Phase 3

- separate shift-level hard legality from seat-level eligibility
- explicitly ingest published/locked/override protection inputs or define the single source of truth
- revalidate preserved assignments through the same hard-constraint pipeline
- remove duplicated soft scoring where a hard constraint already exists
- build a true tie-break ladder
- move rotation from broken score hook to explicit, explainable preference logic
