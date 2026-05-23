# ShiftCommander Base44 Bridge

## Current Architecture

- ShiftCommander remains the source of truth.
- The local backend runs from `E:\GitHub\shiftcommander_v2` with `python server.py`.
- Local backend URL: `http://127.0.0.1:5000`.
- Cloudflare Tunnel should publish the local backend as `https://sc-api.adr-fr.org`.
- Base44 should call backend functions/proxies that target the stable public URL. Do not move data ownership into Base44.

## Local Test Commands

Run these from PowerShell after the backend starts:

```powershell
irm http://127.0.0.1:5000/api/health
irm http://127.0.0.1:5000/api/base44/manifest
irm http://127.0.0.1:5000/api/bootstrap
irm http://127.0.0.1:5000/api/schedule
```

`POST /api/generate` can be tested with:

```powershell
irm -Method Post http://127.0.0.1:5000/api/generate
```

## Public URL Target

Preferred public API hostname:

```text
https://sc-api.adr-fr.org
```

Base44 should receive that stable base URL after the named Cloudflare Tunnel is configured and verified.

## Cloudflare Named Tunnel Setup

`C:\Tools\cloudflared.exe` is the expected local binary path.

If it is missing:

1. Create `C:\Tools`.
2. Download `cloudflared-windows-amd64.exe` from the latest Cloudflare release:
   `https://github.com/cloudflare/cloudflared/releases/latest`
3. Save it as `C:\Tools\cloudflared.exe`.

One-time named tunnel setup:

```powershell
C:\Tools\cloudflared.exe tunnel login
C:\Tools\cloudflared.exe tunnel create shiftcommander-api
C:\Tools\cloudflared.exe tunnel route dns shiftcommander-api sc-api.adr-fr.org
```

Create `%USERPROFILE%\.cloudflared\config.yml`:

```yaml
tunnel: <TUNNEL-UUID-FROM-CREATE>
credentials-file: C:\Users\<YOUR-WINDOWS-USER>\.cloudflared\<TUNNEL-UUID-FROM-CREATE>.json
ingress:
  - hostname: sc-api.adr-fr.org
    service: http://127.0.0.1:5000
  - service: http_status:404
```

Then test:

```powershell
C:\Tools\cloudflared.exe tunnel --config $env:USERPROFILE\.cloudflared\config.yml run
irm https://sc-api.adr-fr.org/api/base44/manifest
```

Random `trycloudflare.com` URLs are temporary and should not be used long term for Base44. Use the named tunnel and `https://sc-api.adr-fr.org`.

## Startup Scripts

Manual backend:

```powershell
E:\GitHub\shiftcommander_v2\ops\start_shiftcommander_backend.bat
```

Manual tunnel:

```powershell
E:\GitHub\shiftcommander_v2\ops\start_shiftcommander_tunnel.bat
```

Install startup Scheduled Tasks:

```powershell
powershell -ExecutionPolicy Bypass -File E:\GitHub\shiftcommander_v2\ops\install_shiftcommander_startup_tasks.ps1
```

Tasks created:

- `ShiftCommander Backend`
- `ShiftCommander Cloudflare Tunnel`

Both run at user logon and log to:

```text
E:\GitHub\shiftcommander_v2\ops\logs\
```

## Test After Reboot

1. Sign into Windows.
2. Wait 30 seconds.
3. Check local backend:

```powershell
irm http://127.0.0.1:5000/api/health
irm http://127.0.0.1:5000/api/base44/manifest
```

4. Check Scheduled Task state:

```powershell
Get-ScheduledTask -TaskName "ShiftCommander Backend"
Get-ScheduledTask -TaskName "ShiftCommander Cloudflare Tunnel"
Get-ScheduledTaskInfo -TaskName "ShiftCommander Backend"
Get-ScheduledTaskInfo -TaskName "ShiftCommander Cloudflare Tunnel"
```

5. Check logs:

```powershell
Get-Content E:\GitHub\shiftcommander_v2\ops\logs\backend_task.log -Tail 80
Get-Content E:\GitHub\shiftcommander_v2\ops\logs\tunnel_task.log -Tail 120
```

6. Check public tunnel:

```powershell
irm https://sc-api.adr-fr.org/api/health
irm https://sc-api.adr-fr.org/api/base44/manifest
```

## Base44 Handoff

After the named tunnel resolves and returns JSON, give Base44:

```text
Base URL: https://sc-api.adr-fr.org
Manifest: https://sc-api.adr-fr.org/api/base44/manifest
Bootstrap: https://sc-api.adr-fr.org/api/bootstrap
Schedule source of truth: https://sc-api.adr-fr.org/api/schedule
Generate schedule: POST https://sc-api.adr-fr.org/api/generate
```

Base44 should call backend functions/proxies, not browser-side localhost URLs.
