# Confirmed Scheduling Rules

Updated: 2026-05-01  
Project: ShiftCommander

This document is the current operational rule baseline for ShiftCommander. It defines the target scheduling doctrine for Supervisor, Member, Resolver, Wallboard, and Mobile workflows.

## 1. Base Schedule

- Fixed 12-hour 2-2-3 backbone.
- Standard shifts are `0600-1800` and `1800-0600`.
- Partial coverage may split a 12-hour seat into 6-hour blocks.
- Supervisor supplies required unit count per shift.
- Resolver may choose staffing pattern based on coverage, cost, ALS preservation, and rules.

## 2. Units

- Support up to 3 units now, with future expansion.
- Unit types include ambulance and QRV.
- Future NEMT support should remain possible.

## 3. ALS Coverage Rule

- County expectation is that each patient receives ALS assessment.
- System must support ALS coverage by either:
  - ALS ambulance attendant
  - ALS QRV
- If ALS QRV is assigned, BLS ambulances may be acceptable.
- ALS preservation is a high-priority doctrine concern.

## 4. Seats

### Ambulance seats

- `ATTENDANT`
  - goal: ALS
  - fallback: EMT
- `DRIVER`
  - goal: EMT with `qualOp` for the specific unit
  - fallback: NMLD with `qualOp`
- `3RD_RIDER`
  - optional
  - EMS student or volunteer only when allowed

### QRV seats

- `ATTENDANT`
  - ALS
- `3RD_RIDER`
  - optional

### Seat management

- Seats must be editable per shift.
- Seat requirements may be supervisor-defined.
- Seat requirements should eventually be dynamically adjustable by allowed rules.

## 5. Member Qualifications

### Supported certifications

- ALS
- AEMT
- Paramedic
- EMT
- EMR
- NMLD
- Student
- FF

### Qualification rules

- Higher certifications may fill lower seats only as a last-resort, high-penalty fallback.
- Driving is controlled by separate `qualOp` flags per unit, for example:
  - `qual_op_120`
  - `qual_op_121`
  - `qual_op_131`
  - `qual_op_QRV1`
- EMT/ALS members may hold a driver license but still cannot drive a unit unless they have that unit's `qualOp`.
- NMLD means licensed non-medical driver and is the lowest acceptable driver fallback.
- Driver fallback must not go below licensed driver.

## 6. Roles

Supported member roles:

- FTO
- Officer
- Salary
- FT
- PT
- PRN

## 7. Hours And OT

### Default hour rules

- Default max weekly hours: 40.
- FT minimum target: 36 hours/week.
- Salary members may be available around 50 hours/week and do not calculate OT the same way.
- Volunteers capped at 24 hours/week.
- Member-specific limits must be supported.

### OT relaxation defaults

- More than 3 weeks out: strict no OT
- 2 to 3 weeks out: soft allow
- 1 to 2 weeks out: moderate allow
- Less than 72 hours: emergency / anything allowed, while still preserving hard safety and certification rules

These windows and meanings must be editable in Supervisor settings.

## 8. Availability

- Statuses:
  - Preferred
  - Available
  - Do Not
  - Blank
- Blank is treated as Do Not.
- Partial availability is allowed.
- Minimum partial block: 6 hours.
- Repeating availability patterns should be supported eventually.
- Members may freely change availability until lock horizon.
- After lock horizon, changes become request / release / swap workflows, not automatic removals.

## 9. Publish And Lock

- Visible horizon default: 8 weeks.
- Once visible, resolver should not reshuffle assignments merely to improve score.
- Lock horizon default: 2 weeks.
- Inside lock horizon, assigned members remain responsible unless swap/drop is accepted and reassigned.
- Supervisor overrides must be locked from future resolver changes.
- Supervisor may reopen a published shift, with logging.

## 10. Weekly Publish

- Wednesday `23:59` is the weekly publish boundary.
- Resolver runs continuously before publish as availability changes.
- Wednesday `23:59` is the final run before revealing/publishing the next period.
- After publishing, assignments should not automatically change except for released, dropped, open, or unresolved seats.

## 11. Open Shifts

- Resolver may leave seats `OPEN` if no good legal fit exists.
- Open critical seats become increasingly visible as they approach today.
- At 3 weeks out, unresolved ALS, legal-driver, or other open critical seats should notify Supervisor.

### Hybrid open-shift claiming

1. collect interested/Preferred candidates
2. resolver scores legal candidates
3. highest score gets first offer
4. offer expires after configured response window
5. next scored candidate is offered
6. if all windows expire, seat may become first-come among legal candidates

- Notify selected candidate by text/email.
- Supervisor should see offer status.

## 12. Fairness

- Fairness uses a combination of:
  - number of shifts/hours assigned, weighted heavily because it affects current income
  - historical percent of Preferred shifts granted, weighted lower but still meaningful
- Seniority is not a factor.
- Preference abuse must be prevented by normalizing or diluting preference value when members mark too many shifts as Preferred.
- Selective preference should carry more value than marking everything Preferred.

## 13. Resolver Priority

Priority order:

1. certification and legal qualification
2. availability
3. ALS preservation
4. avoid OT / stay within budget
5. preference
6. fairness

## 14. Supervisor Workflow

- Supervisor defines shift structure and desired unit count.
- Supervisor may drag/drop assignments.
- Supervisor may override resolver.
- Overrides are protected from future resolver runs.
- Override reason should be logged.
- Supervisor has full control with logging.

## 15. Wallboard

- Display 6 to 8 weeks out.
- Weekly rows.
- Two 12-hour shifts per day.
- Group by date, then shift, then unit, then seat.
- Show open seats.
- Open seats get more urgent visually as they approach today.
- Night theme preferred.
- Names and dates should be the focus.
- Certifications should not be overtly shown, but name color may indicate level:
  - ALS green
  - BLS blue
  - third rider black
  - NMLD pink

## 16. Mobile

- Full schedule visible up to hidden horizon.
- Equal priorities:
  - my shifts
  - who is on shift now
  - pick up open shifts
  - full schedule
- Members choose preferred contact methods:
  - call
  - text
  - email
- Support tap-to-call, tap-to-text, and email links.

## 17. Swaps

- Members may request swaps.
- Same-week two-member swaps may be approved by system without supervisor if:
  - both members consent
  - certifications match
  - `qualOp` rules are satisfied
  - consecutive shift/hour rules are satisfied
  - no hard rules are violated
- No third party can claim fairness violation on a voluntary two-person swap.
- Swap/release workflow should be logged.

## 18. Failure And Alerts

### Critical failures

- no ALS coverage
- no legal driver
- excessive OT/budget risk
- unfilled required ambulance seat

These are not critical until 3 weeks out, but they should be visible before then.

- At 3 weeks out, notify manager/supervisor aggressively.
- Supervisor dashboard should show approaching failures.

## 19. Cost

- Most members are hourly; some are salary.
- Resolver must eventually know pay type and rate.
- Optimization should consider:
  - coverage
  - OT avoidance / budget
  - fairness
  - preference
- Payroll integration is not required.
- Reporting is required for:
  - hours
  - OT
  - fairness
  - budget risk

## 20. Security

- Member login required.
- Supervisor login required.
- Members only edit their own data.
- Supervisor controls all data with logging.
- Debug files are internal only.

## 21. Data And Source Of Truth

- The exact runtime source-of-truth structure is still a design decision.
- The goal is to avoid duplicate runtime truth.
- Static fallbacks require explicit justification if kept.
- Cleanup decisions should preserve one authoritative live scheduling path for:
  - Supervisor
  - Member
  - Resolver
  - Wallboard
  - Mobile
