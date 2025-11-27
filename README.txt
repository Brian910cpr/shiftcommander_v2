ShiftCommander v2 – Multi-View Scheduler Skeleton

This is a working skeleton for the ShiftCommander project with 4 views:

1) Public Wallboard
2) Employee Scheduling (Member) View
3) Manager (Officer) View
4) Admin Setup View

Backend: Python + Flask (simple to run locally)
Frontend: Plain HTML + Vanilla JS (no build step)

Directory layout
----------------
backend/
  __init__.py
  models.py          # dataclasses for members, shifts, units, org settings
  storage.py         # JSON persistence
  api.py             # Flask API exposing 4-view endpoints

data/
  members.json       # demo members with position_type and expected hours
  units.json         # demo units / ambulances
  shifts.json        # demo shifts
  org_settings.json  # display templates, self-scheduling mode, rotation
  assignments.json   # created when schedule is generated (placeholder)

frontend/
  index.html         # UI with 4 tabs (Public, Member, Manager, Admin)
  app.js             # JS to call the API and render views
  styles.css         # Simple styling for readability

How to run (basic dev)
----------------------
1) Create a virtual environment and install Flask:

   python -m venv venv
   venv\Scripts\activate       (Windows)
   source venv/bin/activate      (macOS/Linux)

   pip install flask

2) From this project folder, run:

   python -m backend.api

3) Open the frontend in a browser:

   Option A (recommended):
     - Install "Live Server" extension in VS Code and open frontend/index.html
     - Or run a simple HTTP server from the frontend folder:
       cd frontend
       python -m http.server 8000
     - Then open http://127.0.0.1:8000 in your browser.

   Option B (very simple but less ideal for CORS):
     - Just open frontend/index.html directly from disk.
     - If your browser blocks API calls due to CORS, use the http.server method above.

4) In the UI:
   - Use the "Public" tab to see the wallboard with display-name templates applied.
   - Use the "Member" tab and select a member to view their schedule.
   - Use the "Manager" tab to see coverage and toggle equipment status / 1st-out override.
   - Use the "Admin Setup" tab to change display templates and self-scheduling mode.

Notes
-----
- This is a skeleton: the goal is to show the flow, views, and core data model,
  not to be a complete production-ready system.
- All key concepts are represented:
  * Position types: Full-time / Part-time / Volunteer
  * Expected hours ranges
  * Display-name templates (Initials, Member Number, First/Last combinations)
  * Public vs Member vs Manager vs Admin views
  * First-out rotation with per-shift override capability

From here we can:
- Replace the in-memory demo data with a real database.
- Expand the scheduling algorithm to use your fairness rules.
- Add authentication and per-agency multi-tenant support.
- Wire this into Cloudflare Workers or another hosting platform.
