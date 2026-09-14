# Issue 214: owner inputs accepted on September 14, 2026

Brian approved Brett Toney, Lynnsey Benson and Brian Ennis as the initial supervisors. He supplied a 22-member starter roster and explicitly accepted that missing people can be added after seeing the workflow. The starter roster is approved for initial work; it is not permission to manufacture current availability, credential currency, unit-driver permissions or staffing demand.

## Concrete change

Only `data/members.json` member 186 gains `access.supervisor=true`. Members 159 and 188 retain existing access. All 41 application records and other fields are unchanged. The application role helper returns exactly these three supervisor IDs.

## Source continuity

The approved source already exists as `members.json` in the owner-designated `ShiftCommanderData` Drive folder. Exact source/Drive byte equality, 22 unique source IDs, the matching 22-row CSV map and aggregate reconciliation counts are in `data/audit/owner_intake_20260914.json`. Personnel source files and full conflict rows are retained privately outside Git. Do not overwrite the richer application roster with the older file.

The folder contains 54 historical/configuration files and seven duplicate availability names. Refer to Drive file IDs, not names alone. Historical 07:00/19:00 settings do not override confirmed 06:00/18:00 rules. Older availability files remain historical until confirmed. The existing Drive roster already satisfies the requested source copy; additional personnel uploads and sharing changes await the owner's response to the observed anyone-with-link writer setting.

## Remaining technical work

Owner cannot confirm prior bridge-credential rotation; status remains unknown. The affected credential family is `SC_D1_BRIDGE_TOKEN` between the Flask consumer and live-state Worker validator. Prepare a coordinated private replacement and old-credential rejection proof without disclosing values. No credential was inspected or changed here.

Prepare persistent schema-v2 authentication and a private initial demonstration using confirmed supervisor identities. Collect fresh availability through that workflow. Missing roster members alone must not block a demonstration. Production activation, calendar authority changes and release proof remain separate. Cloudflare metadata access was already established by R43.

Validation: local JSON/identity/map/byte-equality checks, exact three-supervisor behavior using the real role helper, and structural equality of every roster field except the authorized addition. No login/account provisioning, live data change, deployment, integration test or full release is claimed.
