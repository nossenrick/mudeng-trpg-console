param([switch]$Local)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$systemPython = "C:\Users\Zengx\AppData\Local\Programs\Python\Python312\python.exe"
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$sitePackages = Join-Path $PSScriptRoot ".venv\Lib\site-packages"

if (-not (Test-Path $venvPython)) {
  Write-Host "首次运行：正在创建虚拟环境并安装依赖…"
  if (-not (Test-Path $systemPython)) {
    Write-Host "找不到 Python 3.12：$systemPython"
    exit 1
  }
  & $systemPython -m venv (Join-Path $PSScriptRoot ".venv")
  & $venvPython -m pip install --upgrade pip --quiet
  & $venvPython -m pip install -r (Join-Path $PSScriptRoot "requirements.txt") --quiet
}

# Keep the command in a path allowed by the existing Windows Python firewall rule.
$python = if (Test-Path $systemPython) { $systemPython } else { $venvPython }
$env:PYTHONPATH = $sitePackages

$port = 8000
$bindHost = if ($Local) { "127.0.0.1" } else { "0.0.0.0" }
if ($Local) {
  Write-Host "本机模式：只有这台电脑可以访问。"
} else {
  $tailscaleService = Get-Service -Name Tailscale -ErrorAction SilentlyContinue
  if ($tailscaleService -and $tailscaleService.Status -ne "Running") {
    Start-Service Tailscale -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
  if (Get-Command tailscale -ErrorAction SilentlyContinue) {
    & tailscale up 2>$null | Out-Null
  }
  Write-Host "联机模式：本机所有网卡监听，Tailscale/局域网设备可连接。"
  Write-Host "Tailscale 地址：http://100.112.117.110:$port/"
}
Write-Host "本机地址：http://localhost:$port"
Write-Host "AI 密钥只保存在服务端的 ai_config.json 中，不会发送到浏览器。"
& $python -m uvicorn server:app --host $bindHost --port $port
