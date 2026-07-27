# ShiftCommander Supabase implementation status

## Persisted foundation

The files in `supabase/migrations/` are the two migrations recorded in the
live ShiftCommander project's migration history on July 25, 2026:

- `20260725132342_initial_shiftcommander_backbone.sql`
- `20260725132420_add_foreign_key_indexes.sql`

They define private operational (`sc_core`), resolver (`sc_resolver`), and
audit (`sc_audit`) schemas plus a deliberately limited `api` schema.

Raw operational schemas are revoked from `public`, `anon`, and
`authenticated`. The browser must not receive a service-role or secret key.
Application access should be added later through reviewed API views/functions
and role-specific policies.

## Visible dry-run workbench

Open `docs/staffing-workbench.html` directly in a browser. It is a standalone,
local-only staffing simulator that lets a reviewer:

1. choose Normal, Parade, Hurricane, or Funeral staffing;
2. activate or remove resources;
3. add seats to resources;
4. change sample member availability;
5. run a deterministic mock seating pass;
6. inspect assignments and unresolved-seat reasons.

The workbench does not write to Supabase or the current JSON/D1 runtime. It is
an intentionally safe product mock for discovering workflow and rule problems
before a production adapter is introduced.

## Verified live state

- Supabase project: `ShiftCommander`
- Project ref: `cskcgwjvgsgawxwncjrf`
- Region: `us-east-1`
- Status inspected: `ACTIVE_HEALTHY`
- Applied migrations inspected: 2
- Security advisor findings: 0

The generic table listing warns that RLS is disabled on the private schemas.
Those schemas are not granted to browser roles and are omitted from the local
Data API schema list. RLS should still be added as defense in depth alongside
the actual Admin/Supervisor/Member authorization model, not enabled blindly
without policies.
