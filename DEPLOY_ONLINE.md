# ShiftCommander Online Deploy

Build code: `SC-BUILD-2026-05-04-ONLINE-AUTH-QT-001`

## Required environment

- `PORT`
- `SC_QUICK_TEST_MODE`
- `SC_ALLOWED_ORIGINS`
- `SC_PUBLIC_BASE_URL`
- `SECRET_KEY`

Example:

```text
PORT=5000
SC_QUICK_TEST_MODE=true
SC_ALLOWED_ORIGINS=https://adr-fr.org,https://www.adr-fr.org
SC_PUBLIC_BASE_URL=https://shiftcommander-v2.onrender.com
SECRET_KEY=replace-this
```

## Render setup

This repo now includes:

- [render.yaml](E:\GitHub\shiftcommander_v2\render.yaml)

Configured web service:

- service name: `shiftcommander-backend`
- build command: `pip install -r requirements.txt`
- start command: `python -m gunicorn server:app --bind 0.0.0.0:$PORT`
- health check path: `/api/health`

Expected Render backend URL:

- `https://shiftcommander-v2.onrender.com`
- health check URL: `https://shiftcommander-v2.onrender.com/api/health`

If Render forces a different service slug, use the actual Render-assigned hostname instead.

## Preferred production architecture

Best:

- `adr-fr.org` serves the Flask app directly, or
- `adr-fr.org` reverse proxies the Flask app for:
  - `/api/*`
  - `/member`
  - `/login`
  - `/login.html`
  - `/docs/member.html`
  - `/docs/supervisor.html`
  - `/docs/wallboard.html`

Reason:

- member login depends on the Flask session cookie
- cookie auth is cleanest when frontend and backend share the same site
- static-only hosting cannot provide `/api/login`, `/api/auth/session`, or `/api/member/context`

## Cross-origin testing mode

Acceptable for temporary testing:

- static frontend on one origin
- Flask backend on another origin
- set `localStorage.sc_api_base_url` to the backend origin

Limits:

- API calls can work because the backend sends CORS headers
- cookie-backed login may still fail across different sites because browser cookie policy depends on `SameSite`, credentials, and cookie domain behavior

Use this only for testing. Do not treat it as the preferred production architecture.

## Start commands

Local:

```text
python server.py
```

Render / Railway ready:

```text
python -m gunicorn server:app --bind 0.0.0.0:$PORT
```

Render injects `PORT` automatically. `server.py` also binds to `0.0.0.0` for local fallback execution.

If configuring Render manually in the dashboard, use:

- Runtime: Python
- Root directory: blank / repository root
- Branch: `main`
- Build command: `pip install -r requirements.txt`
- Start command: `python -m gunicorn server:app --bind 0.0.0.0:$PORT`
- Health check path: `/api/health`
- Auto deploy: enabled for `main`

## Required backend endpoints

These routes are present in the app and should be checked after deploy:

- `/api/health`
- `/api/members`
- `/api/member/context`
- `/api/login`

## Quick Test Mode

When `SC_QUICK_TEST_MODE=true`:

- `/member` and `/docs/member.html` do not require login
- `docs/member.html` shows the Quick Test banner and member selector
- `/api/member/context` accepts `?member_id=...`
- `/api/member/availability` accepts `member_id`
- `/api/members` returns the member list without supervisor auth

When `SC_QUICK_TEST_MODE=false`:

- real login is required
- `/login` and `/login.html` are the entry point
- `/api/login` sets the Flask session cookie
- `/member` redirects to `docs/member.html` only after auth
