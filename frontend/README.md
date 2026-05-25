# ShiftCommander Frontend Migration

This folder stages the exported Base44 React/Vite UI for migration to a
ShiftCommander-owned frontend.

The exported UI is mostly portable React. Base44 remains in place externally
for now, but this target removes the long-term Base44 app/runtime dependency
from the migrated Vite app.

Local Worker API source of truth:

```text
http://localhost:8787
```

Do not move schedule, member, assignment, resolver, or availability ownership
into the frontend. The frontend should call ShiftCommander backend endpoints.

Google auth is intentionally not implemented in this prep pass. The replacement
`AuthContext` only preserves the expected hook shape and points at backend
session/logout endpoints for later integration.
