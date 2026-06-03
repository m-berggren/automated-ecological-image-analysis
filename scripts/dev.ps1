#requires -version 5
<#
.SYNOPSIS
Run the whole app for local development on Windows: Django API + Vite dev server.

.DESCRIPTION
Starts the Django API (:8000) and the Vue/Vite dev server (:5173) together and
shuts both down on Ctrl+C. Open http://localhost:5173 to use the app.

Uses uv + npm directly if they're on PATH. Otherwise installs mise via winget
(which provides uv + node); because a freshly installed tool isn't on the
current PATH, it then asks you to reopen the terminal and re-run. uv provides
Python 3.13, so there's no separate Python install step.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1

.NOTES
Env overrides: BACKEND_PORT (8000), FRONTEND_PORT (5173).
#>

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$BackendPort  = if ($env:BACKEND_PORT)  { $env:BACKEND_PORT }  else { '8000' }
$FrontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { '5173' }

function Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# ── Toolchain: use uv + npm directly if present, otherwise manage via mise ──
$prefix = @()
if ((Have 'uv') -and (Have 'npm')) {
  # use them directly
}
else {
  if (-not (Have 'mise')) {
    if (-not (Have 'winget')) {
      throw "Neither uv/node nor mise/winget found. Install mise (https://mise.jdx.dev) or uv + Node 24, then re-run."
    }
    Write-Host '==> Installing mise via winget'
    winget install --id jdx.mise -e --source winget --accept-package-agreements --accept-source-agreements
    throw 'Installed mise. Open a NEW terminal (so PATH updates) and re-run this script.'
  }
  Write-Host '==> Ensuring uv + node via mise (mise install)'
  mise install
  $prefix = @('mise', 'exec', '--')
}

# Build a full argv (mise prefix + command) and split into exe + args.
function Invoke-Tool([string[]]$cmd) {
  $all = $prefix + $cmd
  & $all[0] @($all[1..($all.Count - 1)])
  if ($LASTEXITCODE -ne 0) { throw "command failed: $($all -join ' ')" }
}

function Start-Server([string[]]$cmd, [string]$dir) {
  # Start-Process -NoNewWindow uses CreateProcess, which only launches real
  # .exe files. npm is a batch shim (npm.cmd), so launching it directly fails
  # with "%1 is not a valid Win32 application". Route everything through
  # cmd.exe /c so both .cmd shims (npm) and native exes (uv) work; taskkill /T
  # below still tears down the whole tree from the cmd.exe PID.
  $all = $prefix + $cmd
  $line = ($all | ForEach-Object {
    if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
  }) -join ' '
  return Start-Process -FilePath $env:ComSpec `
    -ArgumentList '/c', $line `
    -WorkingDirectory $dir -PassThru -NoNewWindow
}
# ── Dependencies ───────────────────────────────────────────────────────────
Write-Host '==> Syncing Python dependencies (uv sync)'
Invoke-Tool @('uv', 'sync')

if (-not (Test-Path 'frontend/node_modules')) {
  Write-Host '==> Installing frontend dependencies (npm install)'
  Push-Location frontend
  try { Invoke-Tool @('npm', 'install') } finally { Pop-Location }
}

Write-Host '==> Applying database migrations'
Invoke-Tool @('uv', 'run', 'python', 'manage.py', 'migrate')

# ── Run both servers; kill each whole tree (/T) on exit ─────────────────────
# 127.0.0.1 (not 0.0.0.0) keeps the Windows Defender Firewall prompt away.
$root = (Get-Location).Path
$backend = Start-Server @('uv', 'run', 'python', 'manage.py', 'runserver', "127.0.0.1:$BackendPort") $root
$frontend = Start-Server @('npm', 'run', 'dev', '--', '--port', $FrontendPort) (Join-Path $root 'frontend')

Write-Host ''
Write-Host "==> Backend  http://localhost:$BackendPort  (Django API)"
Write-Host "==> Frontend http://localhost:$FrontendPort  <- open this"
Write-Host '==> Ctrl+C stops both'
Write-Host ''

try {
  while (-not $backend.HasExited -and -not $frontend.HasExited) {
    Start-Sleep -Milliseconds 500
  }
}
finally {
  Write-Host "`n==> Shutting down"
  foreach ($p in @($backend, $frontend)) {
    if ($p -and -not $p.HasExited) {
      taskkill /F /T /PID $p.Id 2>$null | Out-Null
    }
  }
}
