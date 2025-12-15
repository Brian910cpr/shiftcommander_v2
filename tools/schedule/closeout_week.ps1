param(
  [Parameter(Mandatory=$true)][string]$DbPath,
  [Parameter(Mandatory=$true)][string]$WeekId,
  [string]$OutRoot = "D:\shiftcommander\private\archive\out\archives",
  [switch]$UseLegacyTables
)

$ErrorActionPreference = "Stop"

function Ensure-Dir([string]$p) {
  New-Item -ItemType Directory -Force -Path $p | Out-Null
}

# Decide schema mode (default: sc_* unless explicitly forced legacy)
$mode = if ($UseLegacyTables) { "legacy" } else { "sc" }

$ts = (Get-Date).ToString("yyyyMMdd_HHmmss")
$bundleDir = Join-Path $OutRoot (Join-Path $WeekId $ts)
Ensure-Dir $bundleDir

$summaryPath = Join-Path $bundleDir "summary.txt"
$csvPath     = Join-Path $bundleDir "seats.csv"
$jsonPath    = Join-Path $bundleDir "seats.json"

# 1) DB backup
$dbBak = "$DbPath.bak_$ts"
Copy-Item -LiteralPath $DbPath -Destination $dbBak -Force

# 2) Export via python (inline, no heredoc)
$py = @"
import json, csv, sqlite3
from pathlib import Path
from datetime import datetime

db = Path(r'''$DbPath''')
week_id = r'''$WeekId'''
mode = r'''$mode'''
csv_path = Path(r'''$csvPath''')
json_path = Path(r'''$jsonPath''')

conn = sqlite3.connect(str(db))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

def fetchone(q, params=()):
    r = cur.execute(q, params).fetchone()
    return dict(r) if r else None

def fetchall(q, params=()):
    return [dict(r) for r in cur.execute(q, params).fetchall()]

exported_at = datetime.now().isoformat(timespec="seconds")

if mode == "legacy":
    wk = fetchone("SELECT * FROM schedule_weeks WHERE week_id = ?", (week_id,))
    if not wk:
        print(f"Week not found in schedule_weeks: {week_id}")
    shifts = fetchall("SELECT * FROM shifts WHERE schedule_week_id = ? ORDER BY start_dt", (week_id,))
    # NOTE: legacy seat table not defined in your dump; leaving placeholder:
    seats = []
else:
    wk = fetchone("SELECT * FROM sc_weeks WHERE week_id = ?", (week_id,))
    if not wk:
        # sc_weeks is authoritative for sc_*
        print(f"Week not found in sc_weeks: {week_id}")
    shifts = fetchall("SELECT * FROM sc_shifts WHERE week_id = ? ORDER BY shift_start", (week_id,))
    seats  = fetchall("""
      SELECT r.*, s.shift_start, s.shift_end, s.label
      FROM sc_seat_records r
      JOIN sc_shifts s ON s.shift_id = r.shift_id
      WHERE s.week_id = ?
      ORDER BY s.shift_start, r.unit_id, r.layer, r.seat_id
    """, (week_id,))

# counts
filled = sum(1 for s in seats if (s.get("health_status") or "").upper() == "FILLED")
unfilled = len(seats) - filled
tag = "HISTORY_DEC2025"
tagged = sum(1 for s in seats if (s.get("note") or "").find(tag) >= 0)

# write JSON
json_path.write_text(json.dumps({
  "exported_at": exported_at,
  "week_id": week_id,
  "mode": ("sc_*" if mode=="sc" else "legacy"),
  "week": wk,
  "shifts": shifts,
  "seats": seats
}, indent=2), encoding="utf-8")

# write CSV (seat rows)
if seats:
    cols = sorted({k for row in seats for k in row.keys()})
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in seats:
            w.writerow(row)
else:
    csv_path.write_text("", encoding="utf-8")

print("EXPORT SUMMARY (v3)")
print(f"  exported_at:   {exported_at}")
print(f"  week_id:       {week_id}")
print(f"  mode:          {'sc_*' if mode=='sc' else 'legacy'}")
print(f"  shifts:        {len(shifts)}")
print(f"  seat_rows:     {len(seats)}")
print(f"  filled:        {filled}")
print(f"  unfilled:      {unfilled}")
print(f"  tagged({tag}): {tagged}")
print("  outputs:")
print(f"    {csv_path}")
print(f"    {json_path}")

conn.close()
"@

python -c $py | Tee-Object -FilePath $summaryPath

# 3) Checksum
$hash = (Get-FileHash -Algorithm SHA256 $jsonPath).Hash

# 4) (Optional) Mark week closed/archived in sc_weeks if present
$py2 = @"
import sqlite3
from pathlib import Path
db = Path(r'''$DbPath''')
week_id = r'''$WeekId'''
conn = sqlite3.connect(str(db))
cur = conn.cursor()
# Only touch sc_weeks if it exists (safe no-op otherwise)
tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
if "sc_weeks" in tables:
    # choose whatever status word you want; keeping 'ARCHIVED'
    cur.execute("UPDATE sc_weeks SET status = COALESCE(status,'DRAFT') WHERE week_id = ?", (week_id,))
conn.commit()
conn.close()
"@
python -c $py2 | Out-Null

"`nCLOSEOUT COMPLETE" | Add-Content -Path $summaryPath
"  Week:     $WeekId" | Add-Content -Path $summaryPath
"  Bundle:   $bundleDir" | Add-Content -Path $summaryPath
"  DB bak:   $dbBak" | Add-Content -Path $summaryPath
"  SHA256:   $hash" | Add-Content -Path $summaryPath

Write-Host ""
Write-Host "CLOSEOUT COMPLETE"
Write-Host "  Week:     $WeekId"
Write-Host "  Bundle:   $bundleDir"
Write-Host "  DB bak:   $dbBak"
Write-Host "  SHA256:   $hash"
Write-Host ""
Write-Host "Paste this file into ChatGPT for verification:"
Write-Host "  $summaryPath"

