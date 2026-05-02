# Project Boundaries

Repo: `E:\GitHub\shiftcommander_v2`  
Project: ShiftCommander

## 1. This Repo Is ShiftCommander Only

This repository is for crew scheduling, assignment resolution, supervisor workflows, member workflows, wallboard display, and related scheduling data handling.

## 2. 910CPR / Enrollware / Lander Concepts Do Not Belong Here

Do not analyze this repo using:

- 910CPR terminology
- Enrollware terminology
- lander terminology
- course or class-session terminology
- HOVN terminology
- CPR training product assumptions

Those concepts belong to a different project and create false architectural conclusions if imported here.

## 3. Use ShiftCommander Terminology Only

Use these meanings consistently:

- `schedule`: EMS/fire crew schedule
- `shift`: duty period
- `unit` or `truck`: apparatus/ambulance/resource being staffed
- `seat`: required staffing position on a unit
- `member`: responder/employee/volunteer
- `assignment`: member placed into a seat
- `availability`: member availability to work
- `wallboard`: schedule display
- `resolver`: assignment engine that fills seats from members and availability

Avoid reframing these concepts as classes, appointments, registrations, courses, or booking inventory.

## 4. Source Of Truth Must Be Evaluated For EMS Scheduling Files Only

When reviewing data sources, backups, stale copies, mirrors, or generated outputs, evaluate them only in terms of EMS/fire scheduling behavior:

- live schedule sources
- shift demand sources
- member roster sources
- availability sources
- assignment outputs
- wallboard/static fallback outputs
- resolver debug outputs

Questions about source of truth should be framed as:

- Which file drives the live schedule?
- Which file drives availability?
- Which file drives member identity and assignment eligibility?
- Which copies are stale or duplicated?
- Which fallback files can surface stale schedules or stale assignments?

## 5. Cleanup Decisions Must Support Scheduling Workflows

Cleanup decisions must support these ShiftCommander workflows:

- Supervisor workflow
- Member workflow
- Resolver workflow
- Wallboard workflow
- Mobile scheduling workflow

Files should not be kept or removed based on unrelated product assumptions. They should be evaluated by whether they help or hurt crew scheduling correctness, clarity, and maintainability.
