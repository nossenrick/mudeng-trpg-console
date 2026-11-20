param(
  [int]$StartPort = 8000,
  [int]$EndPort = 8010,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $project
$python = Join-Path $project ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
  Write-Host "Virtual environment not found. Run launch_trpg.ps1 once first."
  Read-Host "Press Enter to close"
  exit 1
}

function Test-PortFree([int]$Port) {
  $existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if ($existing) { return $false }
  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $Port)
    $listener.Start()
    $listener.Stop()
    return $true
  } catch {
    return $false
  }
}

$port = 0
for ($candidate = $StartPort; $candidate -le $EndPort; $candidate += 1) {
  if (Test-PortFree $candidate) { $port = $candidate; break }
}
if ($port -eq 0) {
  Write-Host "No free port in $StartPort-$EndPort. Close the program using it and retry."
  Read-Host "Press Enter to close"
  exit 1
}

$command = "& '$python' -m uvicorn server:app --host 0.0.0.0 --port $port"
$arguments = "-NoExit -NoProfile -ExecutionPolicy Bypass -Command `"$command`""
Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WorkingDirectory $project | Out-Null

$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt += 1) {
  Start-Sleep -Milliseconds 500
  try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 1
    if ($health.ok) { $ready = $true; break }
  } catch {}
}
if (-not $ready) {
  Write-Host "Server did not start in 20 seconds. Check the new server window."
  Read-Host "Press Enter to close"
  exit 1
}

Write-Host ""
Write-Host "Mu Deng LAN server is running."
Write-Host "Local:  http://localhost:$port/"
try {
  $ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -ExpandProperty IPAddress -Unique
  foreach ($ip in $ips) { Write-Host "LAN:    http://${ip}:$port/" }
} catch {}
Write-Host ""
Write-Host "Use the LAN address from a device on the same Wi-Fi, Tailscale, ZeroTier or other virtual LAN."
Write-Host "If Windows Firewall blocks it, allow Python on Private networks."
Write-Host "Close the server window to stop hosting."
if (-not $NoBrowser) { Start-Process "http://localhost:$port/" }
Start-Sleep -Seconds 1
