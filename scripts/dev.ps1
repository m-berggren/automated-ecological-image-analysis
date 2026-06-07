#requires -version 5
<#
.SYNOPSIS
Run the whole app for local development on Windows: Django API + Vite dev server.

.DESCRIPTION
Starts the Django API (:8000) and the Vue/Vite dev server (:5173) together and
shuts both down on Ctrl+C. Open http://localhost:5173 to use the app.

Uses uv + npm directly if they're on PATH. Otherwise installs mise inline via
its own PowerShell installer (https://mise.run, no winget required), which
provides uv + node, and keeps going in the same run by calling mise.exe by full
path. uv provides Python 3.13, so there's no separate Python install step.

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
  # Find an existing mise, or install it inline. The mise.run installer drops
  # mise.exe in %USERPROFILE%\.local\bin, which isn't on the current PATH yet,
  # so we reference it by full path instead of forcing a terminal restart.
  $mise = if (Have 'mise') { (Get-Command mise).Source }
          else { Join-Path $env:USERPROFILE '.local\bin\mise.exe' }
  if (-not (Test-Path $mise)) {
    Write-Host '==> Installing mise (https://mise.run)'
    Invoke-RestMethod 'https://mise.run/install.ps1' | Invoke-Expression
  }
  if (-not (Test-Path $mise)) {
    throw "mise not found at $mise after install. Install uv + Node 24 manually (https://docs.astral.sh/uv), then re-run."
  }
  Write-Host '==> Ensuring uv + node via mise (mise install)'
  & $mise trust 2>$null    # trust this repo's mise.toml so install is non-interactive
  & $mise install
  if ($LASTEXITCODE -ne 0) { throw 'mise install failed.' }
  $prefix = @($mise, 'exec', '--')
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

# Ensure a login exists on a fresh DB. createsuperuser --noinput reads the
# password from DJANGO_SUPERUSER_PASSWORD; it exits non-zero if 'admin' already
# exists, which is fine (idempotent), so swallow that.
Write-Host '==> Ensuring admin superuser (admin / admin123)'
$env:DJANGO_SUPERUSER_PASSWORD = 'admin123'
try {
  Invoke-Tool @('uv', 'run', 'python', 'manage.py', 'createsuperuser',
                '--noinput', '--username', 'admin', '--email', 'admin@example.com')
}
catch { Write-Host '    (admin already exists; leaving it as is)' }

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
