# Base44 Frontend Migration Checklist

Source of truth: `D:\Users\ten77\Downloads\Pasted markdown.md`.

## Target Folder Structure

```text
frontend/
  index.html
  vite.config.js
  tailwind.config.js
  package.json
  src/
    main.jsx
    App.jsx
    index.css
    api/
      client.js
    lib/
      shiftDisplayRules.js
      apiAdapter.js
      scheduleData.js
      SCIdentityContext.jsx
      useSCIdentity.js
      useWallboardDisplay.js
      useScheduleData.js
      query-client.js
      AuthContext.jsx
    pages/
      Wallboard.jsx
      MemberPage.jsx
      Supervisor.jsx
    components/
      wallboard/
      member/
      mobile/
      supervisor/
      ui/
      SCIdentityGate.jsx
```

The exported `base44/` folder is intentionally not copied into this target.

## Copied As-Is From Export

- `src/lib/shiftDisplayRules.js`
- `src/lib/apiAdapter.js`
- `src/lib/scheduleData.js`
- `src/lib/SCIdentityContext.jsx`
- `src/lib/useSCIdentity.js`
- `src/lib/query-client.js`
- `src/pages/Wallboard.jsx`
- `src/components/wallboard/*`
- `src/components/member/*`
- `src/components/mobile/*`
- `src/components/supervisor/*`
- `src/components/ui/*`
- `src/index.css`
- `tailwind.config.js`
- `components.json`
- Vite/react root files after Base44 plugin removal

## Files Requiring Migration Edits

1. `src/lib/AuthContext.jsx`
   - Replaced Base44 auth internals with a backend-session-shaped stub.
   - Google OAuth/JWT is still TODO.

2. `src/api/base44Client.js`
   - Not copied.
   - Replaced by `src/api/client.js` using plain `fetch`.

3. `src/lib/useWallboardDisplay.js`
   - Replaced `base44.functions.invoke('getWallboardDisplay')`.
   - Now calls `GET /api/wallboard_display` through the shared client.

4. `src/lib/useScheduleData.js`
   - Replaced `base44.functions.invoke('getBootstrap')`.
   - Now calls `GET /api/bootstrap` through the shared client.

5. Logout calls
   - Updated in:
     - `src/components/SCIdentityGate.jsx`
     - `src/pages/Supervisor.jsx`
     - `src/pages/MemberPage.jsx`

6. Direct availability API URL cleanup
   - Updated in:
     - `src/components/member/AvailabilityGrid.jsx`
     - `src/pages/MemberPage.jsx`
   - Calls now flow through `src/api/client.js`.

## Base44-Specific Dependencies Removed From Target

- `@base44/sdk`
- `@base44/vite-plugin`
- `src/api/base44Client.js`
- `src/lib/app-params.js`
- exported `base44/functions/*`
- exported `base44/entities/*`

## Base44-Specific or Migration TODOs Remaining

- Google OAuth/JWT/session verification is not implemented.
- `src/lib/AuthContext.jsx` is a backend-session stub, not production auth.
- `src/components/mobile/MobileMemberPortal.jsx` still has direct
  `https://sc-api.adr-fr.org` availability fetches and should be moved through
  `src/api/client.js` in the first implementation pass.
- `src/components/supervisor/BootstrapStatus.jsx` still displays a hard-coded
  API base fallback string for diagnostics.
- `package-lock.json` from the Base44 export was not kept; regenerate after
  final dependency selection with `npm install`.

## First Safe Implementation Step

Run install/build inside `frontend/`, fix any compile errors from the copied
export, then migrate `MobileMemberPortal` direct availability calls through
`src/api/client.js` before implementing Google auth.
