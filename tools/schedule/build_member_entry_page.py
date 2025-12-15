import re
import json
import sqlite3
from pathlib import Path
from datetime import datetime

def titleize_ph(ph_id: str) -> str:
    # PH_EMS_Supervisor -> "EMS Supervisor"
    s = ph_id
    if s.upper().startswith("PH_"):
        s = s[3:]
    s = s.replace("_", " ").strip()
    # keep capitalization user-friendly
    return " ".join([w[:1].upper() + w[1:] if w else "" for w in s.split(" ")])

def safe_ph_from_name(name: str) -> str:
    # "Brian Ennis" -> PH_Brian_Ennis
    s = re.sub(r"[^A-Za-z0-9]+", "_", name.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "Unknown"
    return f"PH_{s}"

def load_known_placeholders(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Your DB does NOT have sc_placeholders table (per your diagnostics),
        # so we treat placeholder IDs found in sc_seat_records as "known".
        rows = conn.execute("""
            SELECT DISTINCT assigned_placeholder_id AS ph
            FROM sc_seat_records
            WHERE assigned_placeholder_id IS NOT NULL
              AND TRIM(assigned_placeholder_id) <> ''
            ORDER BY ph
        """).fetchall()

        known = []
        for r in rows:
            ph = r["ph"]
            known.append({
                "id": ph,
                "label": titleize_ph(ph)
            })

        return known
    finally:
        conn.close()

def build_html(known: list[dict], db_path: Path, out_html: Path):
    build_info = {
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "db": str(db_path),
        "known_count": len(known),
    }

    known_json = json.dumps(known, indent=2)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>ShiftCommander — Member Entry (Beta)</title>
  <style>
    :root {{
      --bg: #0b1220;
      --card: #111a2e;
      --muted: #7f91b3;
      --text: #e7eefc;
      --line: rgba(255,255,255,.10);
      --good: #17c964;
      --warn: #f5a524;
      --bad: #f31260;
      --accent: #3b82f6;
    }}
    html, body {{ height: 100%; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background: radial-gradient(1200px 600px at 20% 0%, #142246 0%, var(--bg) 45%);
      color: var(--text);
    }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 14px 14px 60px; }}
    .top {{
      display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
      border-bottom: 1px solid var(--line);
      padding: 10px 0 12px;
      margin-bottom: 14px;
    }}
    .top h1 {{ margin: 0; font-size: 18px; letter-spacing: .2px; }}
    .top .sub {{ color: var(--muted); font-size: 12px; margin-top: 4px; }}
    .pill {{
      display: inline-flex; align-items: center; gap: 8px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.04);
      padding: 8px 10px;
      border-radius: 999px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.1fr .9fr;
      gap: 12px;
    }}
    @media (max-width: 980px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
    .card {{
      background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.03));
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      box-shadow: 0 10px 28px rgba(0,0,0,.25);
    }}
    .card h2 {{ margin: 0 0 10px; font-size: 14px; }}
    .row {{ display: grid; grid-template-columns: 180px 1fr; gap: 10px; margin: 10px 0; align-items: center; }}
    .row label {{ color: var(--muted); font-size: 12px; }}
    input, select, textarea {{
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(0,0,0,.25);
      color: var(--text);
      padding: 10px 10px;
      font-size: 14px;
      outline: none;
    }}
    textarea {{ min-height: 70px; resize: vertical; }}
    .btns {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
    button {{
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.06);
      color: var(--text);
      padding: 10px 12px;
      font-weight: 600;
      cursor: pointer;
    }}
    button.primary {{ background: rgba(59,130,246,.22); border-color: rgba(59,130,246,.45); }}
    button.danger {{ background: rgba(243,18,96,.16); border-color: rgba(243,18,96,.35); }}
    .tiny {{ font-size: 11px; color: var(--muted); line-height: 1.35; }}
    .hr {{ height: 1px; background: var(--line); margin: 12px 0; }}
    .two {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }}
    @media (max-width: 620px) {{
      .two {{ grid-template-columns: 1fr; }}
    }}
    .tag {{
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 12px;
      color: var(--muted);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 9px;
      background: rgba(0,0,0,.18);
    }}
    .dot {{ width: 8px; height: 8px; border-radius: 999px; background: var(--accent); display: inline-block; }}
    .rightcol .list {{
      max-height: 360px;
      overflow: auto;
      border-radius: 14px;
      border: 1px solid var(--line);
      padding: 8px;
      background: rgba(0,0,0,.18);
    }}
    .person-item {{
      display: flex; align-items: center; justify-content: space-between; gap: 10px;
      padding: 8px 8px;
      border-bottom: 1px dashed rgba(255,255,255,.08);
      font-size: 13px;
    }}
    .person-item:last-child {{ border-bottom: none; }}
    code {{ color: #b7c9ff; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h1>ShiftCommander — Member Entry (Beta)</h1>
        <div class="sub">Dropdown-only names (no typos). Add-new is allowed, but exported for supervisor import.</div>
      </div>
      <div class="pill" title="Build info">
        <span class="dot"></span>
        built_at: {build_info["built_at"]} • known: {build_info["known_count"]}
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <h2>Enter availability / preferences (hack-beta)</h2>
        <div class="tiny">
          This page is intentionally simple. It stores entries in your browser (localStorage) and exports a JSON bundle you can hand to the scheduler.
        </div>

        <div class="hr"></div>

        <div class="row">
          <label>Person</label>
          <select id="personSelect"></select>
        </div>

        <div class="two">
          <div class="row">
            <label>Week ID</label>
            <input id="weekId" placeholder="WEEK_YYYY-MM-DD_to_YYYY-MM-DD" />
          </div>
          <div class="row">
            <label>Day index (0..6)</label>
            <select id="dayIndex">
              <option value="0">0 (Thu)</option>
              <option value="1">1 (Fri)</option>
              <option value="2">2 (Sat)</option>
              <option value="3">3 (Sun)</option>
              <option value="4">4 (Mon)</option>
              <option value="5">5 (Tue)</option>
              <option value="6">6 (Wed)</option>
            </select>
          </div>
        </div>

        <div class="two">
          <div class="row">
            <label>Slot</label>
            <select id="slot">
              <option value="DAY">DAY (06–18)</option>
              <option value="NIGHT">NIGHT (18–06)</option>
              <option value="BOTH">BOTH</option>
            </select>
          </div>
          <div class="row">
            <label>Role preference</label>
            <select id="rolePref">
              <option value="ANY">Any</option>
              <option value="ATTENDANT">Attendant</option>
              <option value="DRIVER">Driver</option>
              <option value="RIDEALONG">Ride-along</option>
              <option value="NO_DRIVER">Avoid Driver</option>
              <option value="NO_NIGHT">Avoid Night</option>
            </select>
          </div>
        </div>

        <div class="row">
          <label>Availability</label>
          <select id="availability">
            <option value="AVAILABLE">Available</option>
            <option value="UNAVAILABLE">Unavailable</option>
            <option value="PREFERRED">Preferred</option>
            <option value="AVOID">Avoid</option>
          </select>
        </div>

        <div class="row">
          <label>Notes (optional)</label>
          <textarea id="notes" placeholder="e.g., can start at 08:00, needs off by 16:00, etc."></textarea>
        </div>

        <div class="btns">
          <button class="primary" id="saveBtn">Save Entry</button>
          <button id="exportBtn">Export entries.json</button>
          <button class="danger" id="clearBtn">Clear local entries</button>
        </div>

        <div class="hr"></div>

        <h2>Add person (on-the-fly)</h2>
        <div class="tiny">
          Adds a new placeholder like <code>PH_First_Last</code> to the dropdown for this browser.
          You can download <code>new_people.json</code> for a supervisor import later.
        </div>

        <div class="two" style="margin-top:10px;">
          <div class="row">
            <label>Display name</label>
            <input id="newPersonName" placeholder="e.g., Jonah / Sherman / Brian Ennis" />
          </div>
          <div class="row">
            <label>Generated Placeholder ID</label>
            <input id="newPersonId" placeholder="PH_..." readonly />
          </div>
        </div>

        <div class="btns">
          <button id="addPersonBtn">Add to dropdown</button>
          <button id="exportPeopleBtn">Download new_people.json</button>
        </div>

        <div class="tiny" style="margin-top:10px;">
          Tip: For this beta run, it’s totally fine to keep everyone as placeholders.
          Later we’ll swap to real member IDs + auth.
        </div>
      </div>

      <div class="card rightcol">
        <h2>Known names (from DB placeholders)</h2>
        <div class="tiny">These came from <code>sc_seat_records.assigned_placeholder_id</code>. No typos allowed.</div>
        <div class="hr"></div>

        <div class="list" id="knownList"></div>

        <div class="hr"></div>

        <h2>Local saved entries</h2>
        <div class="tiny">What you’ve saved in this browser (localStorage). Export to hand to the scheduler.</div>
        <div class="hr"></div>
        <div class="list" id="entryList"></div>
      </div>
    </div>
  </div>

<script>
  // Embedded from build script:
  const KNOWN = {known_json};

  const STORAGE_KEY_ENTRIES = "sc_beta_entries_v1";
  const STORAGE_KEY_NEWPEOPLE = "sc_beta_new_people_v1";

  function safePH(name) {{
    let s = (name || "").trim();
    s = s.replace(/[^A-Za-z0-9]+/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
    if (!s) s = "Unknown";
    return "PH_" + s;
  }}

  function loadJSON(key, fallback) {{
    try {{
      const raw = localStorage.getItem(key);
      if (!raw) return fallback;
      return JSON.parse(raw);
    }} catch (e) {{
      return fallback;
    }}
  }}

  function saveJSON(key, value) {{
    localStorage.setItem(key, JSON.stringify(value, null, 2));
  }}

  function download(filename, obj) {{
    const blob = new Blob([JSON.stringify(obj, null, 2)], {{ type: "application/json" }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }}

  function renderKnown() {{
    const knownList = document.getElementById("knownList");
    knownList.innerHTML = "";
    for (const k of getAllPeople()) {{
      const div = document.createElement("div");
      div.className = "person-item";
      div.innerHTML = `<span>${{k.label}}</span><span class="tiny"><code>${{k.id}}</code></span>`;
      knownList.appendChild(div);
    }}
  }}

  function getAllPeople() {{
    const added = loadJSON(STORAGE_KEY_NEWPEOPLE, []);
    // Merge unique by id
    const map = new Map();
    for (const k of KNOWN) map.set(k.id, k);
    for (const p of added) map.set(p.id, p);
    return Array.from(map.values()).sort((a,b)=>a.label.localeCompare(b.label));
  }}

  function populatePeopleDropdown() {{
    const sel = document.getElementById("personSelect");
    const people = getAllPeople();
    sel.innerHTML = "";
    for (const p of people) {{
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.label;
      sel.appendChild(opt);
    }}
  }}

  function renderEntries() {{
    const list = document.getElementById("entryList");
    const entries = loadJSON(STORAGE_KEY_ENTRIES, []);
    list.innerHTML = "";
    if (!entries.length) {{
      list.innerHTML = `<div class="tiny">No entries saved yet.</div>`;
      return;
    }}
    for (const e of entries.slice().reverse()) {{
      const div = document.createElement("div");
      div.className = "person-item";
      div.innerHTML = `
        <div>
          <div><strong>${{e.person_label}}</strong> <span class="tiny">(<code>${{e.person_id}}</code>)</span></div>
          <div class="tiny">${{e.week_id}} • D${{e.day_index}} • ${{e.slot}} • ${{e.availability}} • pref: ${{e.role_pref}}</div>
          ${{e.notes ? `<div class="tiny">“${{e.notes}}”</div>` : ""}}
        </div>
        <div class="tiny">${{e.saved_at}}</div>
      `;
      list.appendChild(div);
    }}
  }}

  function personLabelById(id) {{
    const all = getAllPeople();
    return (all.find(p => p.id === id) || {{label:id}}).label;
  }}

  // Wire up add-person section
  const newNameEl = document.getElementById("newPersonName");
  const newIdEl = document.getElementById("newPersonId");
  newNameEl.addEventListener("input", () => {{
    newIdEl.value = safePH(newNameEl.value);
  }});

  document.getElementById("addPersonBtn").addEventListener("click", () => {{
    const name = newNameEl.value.trim();
    if (!name) return alert("Enter a display name first.");
    const id = safePH(name);

    const added = loadJSON(STORAGE_KEY_NEWPEOPLE, []);
    if (!added.find(x => x.id === id)) {{
      added.push({{ id, label: name }});
      saveJSON(STORAGE_KEY_NEWPEOPLE, added);
    }}

    populatePeopleDropdown();
    renderKnown();

    // select the new person
    document.getElementById("personSelect").value = id;

    newNameEl.value = "";
    newIdEl.value = "";
  }});

  document.getElementById("exportPeopleBtn").addEventListener("click", () => {{
    const added = loadJSON(STORAGE_KEY_NEWPEOPLE, []);
    download("new_people.json", {{
      exported_at: new Date().toISOString(),
      people: added
    }});
  }});

  // Save / export entries
  document.getElementById("saveBtn").addEventListener("click", () => {{
    const person_id = document.getElementById("personSelect").value;
    const week_id = document.getElementById("weekId").value.trim();
    const day_index = Number(document.getElementById("dayIndex").value);
    const slot = document.getElementById("slot").value;
    const role_pref = document.getElementById("rolePref").value;
    const availability = document.getElementById("availability").value;
    const notes = document.getElementById("notes").value.trim();

    if (!week_id) return alert("Week ID is required.");

    const entries = loadJSON(STORAGE_KEY_ENTRIES, []);
    entries.push({{
      saved_at: new Date().toISOString(),
      person_id,
      person_label: personLabelById(person_id),
      week_id,
      day_index,
      slot,
      role_pref,
      availability,
      notes
    }});
    saveJSON(STORAGE_KEY_ENTRIES, entries);

    document.getElementById("notes").value = "";
    renderEntries();
  }});

  document.getElementById("exportBtn").addEventListener("click", () => {{
    const entries = loadJSON(STORAGE_KEY_ENTRIES, []);
    download("entries.json", {{
      exported_at: new Date().toISOString(),
      entries
    }});
  }});

  document.getElementById("clearBtn").addEventListener("click", () => {{
    if (!confirm("Clear all local entries in this browser?")) return;
    localStorage.removeItem(STORAGE_KEY_ENTRIES);
    renderEntries();
  }});

  // init
  populatePeopleDropdown();
  renderKnown();
  renderEntries();
</script>
</body>
</html>
"""
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")

def main():
    # EDIT THIS PATH IF NEEDED:
    db_path = Path(r"D:\Users\ten77\Downloads\shiftcommander_sync\ShiftCommander\live\shiftcommander.db")
    out_html = Path(r"D:\shiftcommander\tools\schedule\member_entry\index.html")

    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    known = load_known_placeholders(db_path)
    if not known:
        print("WARNING: No placeholders found in sc_seat_records. Page will still build, but dropdown will be empty.")

    build_html(known, db_path, out_html)
    print(f"OK: wrote {out_html}")
    print("Open it in a browser (file:// is fine). No fetch calls used.")

if __name__ == "__main__":
    main()
