param(
  [int]$StartPort = 8000,
  [int]$EndPort = 8010,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $project

function Get-TrpgServerPort {
  param([int]$From, [int]$To)
  for ($port = $From; $port -le $To; $port += 1) {
    try {
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 1
      if ($health.ok -and $health.service -eq "trpg-host-console") {
        return $port
      }
    } catch {
      # Port is free or belongs to another service.
    }
  }
  return 0
}

function Test-PortFree {
  param([int]$Port)
  $existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if ($existing) { return $false }
  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    $listener.Start()
    $listener.Stop()
    return $true
  } catch {
    return $false
  }
}

try {
  $python = Join-Path $project ".venv\Scripts\python.exe"
  if (-not (Test-Path $python)) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
      throw "找不到 Python，请先安装 Python 3.11 或更高版本。"
    }
    Write-Host "首次运行：创建虚拟环境并安装依赖…"
    python -m venv (Join-Path $project ".venv")
    & $python -m pip install --upgrade pip --quiet
    & $python -m pip install -r (Join-Path $project "requirements.txt") --quiet
  }

  $runningPort = Get-TrpgServerPort -From $StartPort -To $EndPort
  if ($runningPort -gt 0) {
    Write-Host "跑团主持台已经在运行：http://localhost:$runningPort"
    if (-not $NoBrowser) { Start-Process "http://localhost:$runningPort/" }
    Start-Sleep -Seconds 1
    exit 0
  }

  $port = 0
  for ($candidate = $StartPort; $candidate -le $EndPort; $candidate += 1) {
    if (Test-PortFree -Port $candidate) {
      $port = $candidate
      break
    }
  }
  if ($port -eq 0) {
    throw "端口 $StartPort-$EndPort 都被占用了，请先关闭占用端口的程序。"
  }

  $runner = Join-Path $project "run_server_window.ps1"
  $arguments = "-NoExit -NoProfile -ExecutionPolicy Bypass -File `"$runner`" -Port $port"
  Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WorkingDirectory $project | Out-Null

  $ready = $false
  for ($attempt = 0; $attempt -lt 40; $attempt += 1) {
    Start-Sleep -Milliseconds 500
    if ((Get-TrpgServerPort -From $port -To $port) -gt 0) {
      $ready = $true
      break
    }
  }
  if (-not $ready) {
    throw "后端没有在 20 秒内启动，请查看新打开的服务窗口里的错误信息。"
  }

  Write-Host "跑团主持台已启动：http://localhost:$port"
  if (-not $NoBrowser) { Start-Process "http://localhost:$port/" }
  Start-Sleep -Seconds 1
  exit 0
} catch {
  Write-Host ""
  Write-Host "启动失败：$($_.Exception.Message)"
  Write-Host ""
  Read-Host "按回车关闭"
  exit 1
}
