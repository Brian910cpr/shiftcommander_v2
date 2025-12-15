import json
import sqlite3
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import re

DB_PATH = Path(r"D:\Users\ten77\Downloads\shiftcommander_sync\ShiftCommander\live\shiftcommander.db")
HOST = "127.0.0.1"
PORT = 8765

def safe_ph_from_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", name.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "Unknown"
    return f"PH_{s}"

def titleize_ph(ph_id: str) -> str:
    s = ph_id
    if s.upper().startswith("PH_"):
        s = s[3:]
    s = s.replace("_", " ").strip()
    return " ".join([w[:1].upper() + w[1:] if w else "" for w in s.split(" ")])

def ensure_tables(conn: sqlite3.Connection) -> None:
    # Your DB previously had no sc_placeholders/sc_units tables.
    # We create sc_placeholders for "official" name registry.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sc_placeholders (
          placeholder_id TEXT PRIMARY KEY,
          label          TEXT NOT NULL,
          created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_sc_placeholders_label
        ON sc_placeholders(label)
    """)

def load_people(conn: sqlite3.Connection):
    ensure_tables(conn)

    # Prefer sc_placeholders registry
    rows = conn.execute("""
        SELECT placeholder_id AS id, label
        FROM sc_placeholders
        ORDER BY label
    """).fetchall()

    people = [{"id": r[0], "label": r[1]} for r in rows]

    # Fallback/merge: discover placeholders seen in seat records (so nothing disappears)
    seen = conn.execute("""
        SELECT DISTINCT assigned_placeholder_id AS ph
        FROM sc_seat_records
        WHERE assigned_placeholder_id IS NOT NULL
          AND TRIM(assigned_placeholder_id) <> ''
        ORDER BY ph
    """).fetchall()

    existing_ids = {p["id"] for p in people}
    for (ph,) in seen:
        if ph not in existing_ids:
            people.append({"id": ph, "label": titleize_ph(ph)})

    people.sort(key=lambda x: x["label"].lower())
    return people

def upsert_person(conn: sqlite3.Connection, display_name: str):
    ensure_tables(conn)

    display_name = (display_name or "").strip()
    if not display_name:
        raise ValueError("display_name is required")

    ph_id = safe_ph_from_name(display_name)

    # Insert/update by id
    conn.execute("""
        INSERT INTO sc_placeholders (placeholder_id, label)
        VALUES (?, ?)
        ON CONFLICT(placeholder_id) DO UPDATE SET
          label=excluded.label
    """, (ph_id, display_name))

    return {"id": ph_id, "label": display_name}

class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, obj):
        data = json.dumps(obj, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        # CORS for local dev convenience
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def _html(self, code: int, html: str):
        data = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path

        if p == "/" or p == "/index.html":
            html_path = Path(r"D:\shiftcommander\tools\schedule\member_entry\index_live.html")
            if not html_path.exists():
                return self._html(500, f"<h1>Missing file</h1><p>{html_path}</p>")
            return self._html(200, html_path.read_text(encoding="utf-8"))

        if p == "/api/people":
            if not DB_PATH.exists():
                return self._json(500, {"ok": False, "error": f"DB not found: {DB_PATH}"})
            conn = sqlite3.connect(str(DB_PATH))
            try:
                people = load_people(conn)
                return self._json(200, {"ok": True, "people": people})
            finally:
                conn.close()

        return self._html(404, "<h1>404</h1>")

    def do_POST(self):
        p = urlparse(self.path).path

        if p == "/api/add_person":
            if not DB_PATH.exists():
                return self._json(500, {"ok": False, "error": f"DB not found: {DB_PATH}"})

            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                payload = json.loads(body)
            except Exception:
                return self._json(400, {"ok": False, "error": "Invalid JSON body"})

            display_name = (payload.get("display_name") or "").strip()

            conn = sqlite3.connect(str(DB_PATH))
            try:
                person = upsert_person(conn, display_name)
                conn.commit()
                people = load_people(conn)
                return self._json(200, {"ok": True, "added": person, "people": people})
            except Exception as e:
                conn.rollback()
                return self._json(400, {"ok": False, "error": str(e)})
            finally:
                conn.close()

        return self._json(404, {"ok": False, "error": "Not found"})

def main():
    print(f"DB:   {DB_PATH}")
    print(f"URL:  http://{HOST}:{PORT}/")
    print("Stop: Ctrl+C")
    HTTPServer((HOST, PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
