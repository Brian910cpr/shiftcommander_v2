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

Startup data now prefers a single `GET /api/bootstrap` request through
`src/lib/bootstrapData.js`, then normalizes members, schedule, settings,
availability, transactions, wallboard display, and member dashboard state for
frontend hooks. Individual API routes remain fallback/read-only compatibility
routes. Availability writes are intentionally still on the existing member
availability compatibility endpoint.

Google auth is intentionally not implemented in this prep pass. The replacement
`AuthContext` only preserves the expected hook shape and points at backend
session/logout endpoints for later integration.

## Local SPA Preview

The migrated frontend uses React Router `BrowserRouter`. Vite is configured as
an SPA (`appType: 'spa'`) so local dev and preview fall back to `index.html`
for deep links such as `/wallboard`, `/member`, and `/supervisor`.

For Cloudflare Pages, keep `BrowserRouter` and configure a rewrite fallback to
serve `/index.html` for application routes. For GitHub Pages without custom
rewrite support, `HashRouter` is the simpler static-hosting fallback, but it
changes URLs to `/#/member` style routes.
