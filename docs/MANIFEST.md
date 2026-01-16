# ShiftCommander (CLEAN)

This folder is a **distraction-free working set**.

## Canonical apps

- **member.html**  (from `member_beta.html`)
  - Writes: `kind=member_availability`, key: `member_id`
  - Local fallback: `localStorage` keys `sc:avail:<member_id>` + `sc:availmeta:<member_id>`

- **supervisor.html** (from `supervisor_fixed_schedulewrite.html`)
  - Reads/Writes: `kind=org_settings`, `kind=members`
  - Reads: `kind=member_availability` (per member) when resolving
  - Writes: `kind=schedule` when resolving or editing schedule

- **wallboard.html** (from `wallboard_fixed.html`)
  - Reads: `kind=schedule` + `kind=members` (to render names)

## Data files mirrored locally

`data/` contains the minimum JSONs used by the pages (useful for offline dev). In production, the pages read/write via `/api/store`.

## Archived items

Everything noisy (Old_versions, normalized month snapshots, etc.) was packed into:

- `ARCHIVE/archived_noise.zip`

Source files were **not deleted**; this tool only *copies* and *archives*.
