# Resolver Rule Audit

Audit target: `E:\GitHub\shiftcommander_v2`

Status: Phase 1 only. No code changes made.

## Scope

Verified active runtime path:
- `server.py:316` `run_shift_builder()` imports `engine.shift_builder.build_shift_skeletons`
- `server.py:336` `run_resolver()` imports `engine.resolver.resolve`
- `server.py:363` `/api/generate` runs shift builder, then resolver

## Fact vs Inference

- `FACT`: directly observed in code or repo data.
- `INFERENCE`: likely intended behavior or likely impact, but not directly enforced in code.

## Hard Constraints Present Now

### Member identity and double-booking

- `FACT`: `engine/resolver.py` `member_can_fill_seat()` rejects candidates with no member id via `missing_member_id`.
- `FACT`: `member_can_fill_seat()` rejects candidates already assigned in the same shift via `double_booked_same_shift`.

### Probationary gating

- `FACT`: `member_can_fill_seat()` rejects probationary members during `normal` and `reserve` passes with `probationary_reserved_for_training_pass`.
- `FACT`: `member_can_fill_seat()` only allows non-probationary members in `training_third_seat` if they are probationary and the seat is `3RD_RIDER`.
- `FACT`: `probation_allows()` blocks probationary non-3rd-rider core assignments and can require an FTO for phase 1 or phase 2 trainees.

### Availability as a hard gate

- `FACT`: `availability_allows()` is a hard filter.
- `FACT`: candidates are allowed only when status resolves to `PREFERRED` or `AVAILABLE`.
- `FACT`: `DO_NOT_SCHEDULE` rejects with `availability_dns:*`.
- `FACT`: missing availability rejects with `availability_missing:*`.
- `FACT`: `get_availability_status()` prefers exact date availability over pattern availability.

### Role / certification eligibility

- `FACT`: `role_allowed_by_cert()` enforces seat-role eligibility.
- `FACT`: for `DRIVER`, the member must be allowed to drive the unit through `can_drive_unit()`.
- `FACT`: for `ATTENDANT`, `NCLD` is always blocked.
- `FACT`: when `seat_requires_als()` is true, only `ALS` is allowed in `ATTENDANT`.
- `FACT`: otherwise `ATTENDANT` allows `ALS`, `EMT`, or `EMR`.
- `FACT`: `3RD_RIDER` allows `ALS`, `EMT`, `EMR`, or `NCLD`.

### Unit permission

- `FACT`: `unit_permission_allows()` is a hard filter for driver seats.

### Hard weekly cap

- `FACT`: `would_break_hard_cap()` is a hard filter using `get_hard_weekly_cap()`.

### Restricted pairing

- `FACT`: `restricted_pairing_allows()` blocks a candidate if already-assigned same-shift members form a restricted pair from settings.

### ALS-ALS core truck blocking

- `FACT`: `member_can_fill_seat()` contains two separate ALS-pair blocking sections.
- `FACT`: both sections reject an ALS candidate if another assigned core seat already has an ALS member, returning `als_als_pair_block`.
- `FACT`: the second block is labeled as “prevent ALS-ALS pairing on normal two-seat trucks”.
- `FACT`: the first block already blocks the same condition for all `DRIVER`/`ATTENDANT` seats, so the second block is effectively duplicate logic.

### Reserve separation

- `FACT`: `member_can_fill_seat()` blocks reserve members in the `normal` pass with `reserve_held_for_fallback`.
- `FACT`: reserve members can only be considered in the `reserve` pass.

### Training seat activation constraints

- `FACT`: `activate_training_seats()` only activates `3RD_RIDER` seats when an FTO is already assigned and at least one probationary member is availability-eligible.
- `FACT`: inactive training seats are hidden from board output.

## Scoring Rules Present Now

### Base role score

- `FACT`: `seat_role_base_score()` contributes a base score by seat role and cert.
- `FACT`: `DRIVER` base score prefers `EMT` over `NCLD` over `ALS` over `EMR`.
- `FACT`: `ATTENDANT` base score prefers `ALS` over `EMT` over `EMR`, unless ALS is required.
- `FACT`: `3RD_RIDER` base score prefers `ALS` over `EMT` over `EMR` over `NCLD`.

### Rotation bonus

- `FACT`: `score_member_for_seat()` adds `rotation_home_bonus = 25.0` when `member.rotation.role == get_pattern_key_from_shift(shift)`.
- `FACT`: `member.rotation.role` is normalized in `server.py` to `A`, `B`, `C`, or `D`.
- `FACT`: `get_pattern_key_from_shift()` returns values like `MON_AM` or `TUE_PM`.
- `FACT`: this comparison can never match as currently implemented.
- `INFERENCE`: the intended 2-2-3 preference is currently non-functional in active resolver scoring.

### Training-pass scoring

- `FACT`: `training_third_seat` adds a large base bonus, penalizes prior training assignments, adds a phase bonus, rewards `PREFERRED` availability, and penalizes weekly hours.

### ALS driver conservation

- `FACT`: `score_member_for_seat()` applies `als_driver_conservation_penalty` only as a score penalty.
- `FACT`: this is not a hard rule, so ALS drivers remain legal candidates and can still win.

### Full-time minimum protection

- `FACT`: `score_member_for_seat()` adds `ft_minimum_bonus = 100.0` if a full-time member is below their target minimum hours.

### Reserve handling in scoring

- `FACT`: reserve workers get a severe score penalty in `normal` pass and a small bonus in `reserve` pass.
- `FACT`: this is partly redundant because reserve workers are already filtered out of `normal` pass by hard constraint.

### Weekly-hours penalty

- `FACT`: `score_member_for_seat()` subtracts `weekly_hours * 0.25`.

### Preferred availability bonus

- `FACT`: `PREFERRED` availability adds `availability_preferred_bonus`.
- `FACT`: `AVAILABLE` receives no bonus but still passes the hard filter.

### AM/PM preference bonus

- `FACT`: `prefer_am` or `prefer_pm` adds `prefer_ampm_bonus` when the shift label matches.

### 24-hour preference adjustment

- `FACT`: `shift24` preference can add `prefer_24_bonus` or subtract `avoid_24_penalty`.
- `INFERENCE`: this is weakly enforced and may not reflect actual 24-hour assignment structure because the active shift builder creates `AM` and `PM` blocks, not true 24-hour shifts.

### Soft-avoid penalties

- `FACT`: `soft_avoid_penalty` and `mutual_soft_avoid_penalty_bonus` are both score penalties.
- `FACT`: soft-avoid relationships are not hard constraints.

### ALS-required bonus

- `FACT`: when ALS is required and the candidate is ALS, `score_member_for_seat()` adds an additional `als_required_bonus`.
- `INFERENCE`: this bonus is unnecessary once ALS-required attendants are already hard-filtered to ALS only.

### ALS pair penalty

- `FACT`: `score_member_for_seat()` applies an `als_pair_penalty` if another already-assigned member on the shift is ALS.
- `FACT`: this score penalty is redundant in many cases because `member_can_fill_seat()` already blocks ALS-ALS pairings as a hard constraint.

## Missing Rules Relative to Doctrine

- `FACT`: no rule was found that allows `EMT+EMT` only when broader shift ALS coverage exists.
- `FACT`: no shift-level ALS coverage model was found in the active resolver pipeline.
- `FACT`: no published-seat ingestion path was found in `run_resolver()`; it loads `members`, `shifts`, `settings`, and `availability`, but not `schedule_locked.json` or `overrides.json`.
- `FACT`: no explicit “partial availability ranks below full-shift coverage” rule was found.
- `FACT`: no overtime cost scoring or overtime eligibility model was found in active resolver scoring.
- `FACT`: no explicit tie-break policy beyond `(-score, member_id)` sort order was found.
- `FACT`: no legal-combo validator exists as a separate shift-level rule function.
- `FACT`: no explicit fallback audit object exists to explain when a seat was filled by controlled exception instead of normal legality.

## Ambiguous Rules

- `FACT`: `seat_requires_als()` only treats `ATTENDANT` seats as ALS-requiring based on `display_role` or day rule value `ALS`.
- `INFERENCE`: the meaning of `settings.day_rules` values `ALS` and `ALS+EMT` is ambiguous in the active code because only attendant ALS requirements are enforced; broader truck-composition doctrine is not.

- `FACT`: `is_als_fto()` returns true for any ALS member if explicit FTO flags are absent.
- `INFERENCE`: this likely overstates who counts as an FTO for trainee protection.

- `FACT`: `compute_lock_status()` uses only a time window.
- `INFERENCE`: “locked” in the resolver is not the same thing as “published/confirmed/override-protected” in the supervisor UI.

- `FACT`: `preserve_existing_assignments()` preserves all existing assignments without validating legality.
- `INFERENCE`: existing invalid assignments can survive into resolver output if preloaded into `shifts.json` or already assigned in working schedule data.

## Suspected Issues Checklist

### Verified

- `FACT`: active resolver entry point is `engine/resolver.py` called by `server.py`.
- `FACT`: no automated tests were found in the repo.
- `FACT`: rotation support exists in `rotation_engine.py` and UI/data, but active resolver uses only a weak score hook.
- `FACT`: the current rotation match logic is incorrect because track letters are compared to weekday shift pattern keys.
- `FACT`: locking is time-window based in the active resolver.
- `FACT`: existing assignments are preserved without revalidation.
- `FACT`: resolver runs multiple passes with an intermediate unpublished re-evaluation.
- `FACT`: ALS/AEMT normalization exists, but legality, fallback, and scoring remain entangled.

### Additional audit finding

- `FACT`: `scripts/build_draft_schedule.py` imports `build_schedule` from `server.py`, but no such function exists in `server.py`.
