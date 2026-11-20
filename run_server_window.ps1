param(
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $project

$Host.UI.RawUI.WindowTitle = "跑团主持台 - 联机模式 :$Port"
Write-Host "跑团主持台后端（联机模式）"
Write-Host "本机地址：http://localhost:$Port"
Write-Host "Tailscale：http://100.112.117.110:$Port"
Write-Host "关闭这个窗口即可停止服务。"
Write-Host ""

$systemPython = "C:\Users\Zengx\AppData\Local\Programs\Python\Python312\python.exe"
$venvPython = Join-Path $project ".venv\Scripts\python.exe"
$sitePackages = Join-Path $project ".venv\Lib\site-packages"
if (-not (Test-Path $venvPython)) {
  Write-Host "找不到虚拟环境，请先运行 launch_trpg.ps1。"
  exit 1
}
$python = if (Test-Path $systemPython) { $systemPython } else { $venvPython }
$env:PYTHONPATH = $sitePackages

$tailscaleService = Get-Service -Name Tailscale -ErrorAction SilentlyContinue
if ($tailscaleService -and $tailscaleService.Status -ne "Running") {
  Start-Service Tailscale -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 2
}
if (Get-Command tailscale -ErrorAction SilentlyContinue) {
  & tailscale up 2>$null | Out-Null
}

& $python -m uvicorn server:app --host 0.0.0.0 --port $Port
