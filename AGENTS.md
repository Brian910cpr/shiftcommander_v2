\# ShiftCommander Supervisor System Rules



\## Core Operational Philosophy



ShiftCommander is an operational staffing system, not a generic scheduling demo.



Primary priorities:



1\. Legal staffing

2\. Operational continuity

3\. Assignment stability

4\. Resolver transparency

5\. Supervisor trust

6\. Auditability

7\. Controlled optimization



A technically elegant schedule is NOT preferred over a trusted and explainable operational schedule.



\## Resolver Hierarchy



Hard constraints are NEVER violated:



\* certification legality

\* seat legality

\* staffing minimums

\* explicit unavailability

\* locked assignments

\* required staffing combinations

\* protected assignment rules



Soft scoring is secondary.



Never sacrifice legality for optimization.



\## Existing Assignment Preservation



Preserve existing assignments whenever possible.



Avoid unnecessary churn.



Do not reshuffle functional schedules merely to improve scores.



Operational stability is preferred over theoretical optimization gains.



\## Preferred Resolver Behavior



Resolver behavior should prioritize:



\* predictable outcomes

\* explainable outcomes

\* minimal surprise

\* visible reasoning

\* reproducibility



When conflicts occur:



\* explain WHY a candidate failed

\* preserve audit traces

\* expose rejection reasons where practical



Avoid opaque “magic” optimization behavior.



\## Scheduling Philosophy



The goal is to create schedules supervisors can TRUST.



The resolver should behave like:



\* an experienced operations lieutenant

\* not a casino optimizer



Minor imperfections are acceptable if:



\* staffing remains legal

\* operational continuity is preserved

\* assignments remain understandable



\## Hard Constraint Rules



The following are considered hard-stop conditions:



\* certification mismatch

\* unavailable member

\* locked seat conflict

\* invalid staffing combination

\* duplicate conflicting assignment

\* explicit protected time blocks

\* seat qualification failure



Do not bypass hard constraints silently.



\## Preferred Optimization Strategy



Prefer:



\* preserving valid schedules

\* minimal changes

\* localized fixes

\* targeted reassignment



Avoid:



\* full-schedule reshuffles

\* chain-reaction optimization

\* unnecessary reassignment cascades

\* global rewrites of stable schedules



When possible, identify the smallest authoritative source capable of solving the issue.



\## Known Good / Stable



The following systems are considered stable unless explicitly targeted:



\* preserve\_existing\_assignments() behavior

\* lock handling logic

\* hard constraint enforcement

\* supervisor audit outputs

\* resolver artifact generation

\* ALS/AEMT historical conversion handling

\* rotation template behavior

\* wallboard rendering logic

\* live /api/schedule merged schedule output



Avoid architectural rewrites of stable systems without explicit request.



\## Debug / Audit Artifacts



These artifacts are authoritative operational diagnostics:



\* latest\_run\_summary.json

\* latest\_run\_supervisor\_cards.json

\* latest\_run\_failures.json

\* latest\_run\_full\_audit.json



Prefer preserving audit visibility over hiding complexity.



\## Preferred Engineering Style



\* Prefer surgical fixes over broad resolver rewrites.

\* Preserve operational quirks if they are relied upon.

\* Preserve historical behavior unless explicitly changing policy.

\* Minimize collateral schedule churn.

\* Preserve supervisor visibility and trust.

\* Prefer deterministic and reproducible outputs.

\* Avoid introducing opaque optimization systems.

\* Favor explainability over abstraction.

\* Favor operational continuity over elegance.



\## Dangerous Areas



Avoid modifying without explicit reason:



\* hard constraint logic

\* preserve\_existing\_assignments()

\* lock interpretation

\* staffing legality checks

\* assignment persistence

\* audit generation

\* wallboard live schedule behavior



Small logic changes in these systems can create massive operational side effects.



\## Build / Validation Expectations



Before completion:



\* run syntax validation where practical

\* validate resolver legality

\* validate no hard constraints are violated

\* validate audit outputs still generate

\* validate supervisor-facing visibility still functions



Clearly distinguish:



\* locally validated

\* dry-run validated

\* deployed

\* sandbox-only



\## Operational Trust Rules



Supervisor confidence matters.



Prefer:



\* stable schedules

\* visible logic

\* explainable outcomes

\* predictable assignment behavior



Avoid:



\* “AI magic”

\* unexplained reshuffling

\* unstable optimization loops

\* hidden fallback behavior



\## Repository Philosophy



This repository is operational infrastructure.



The system must remain:



\* understandable

\* auditable

\* maintainable

\* legally reliable

\* operationally predictable



Prefer practical operational reliability over theoretical perfection.



