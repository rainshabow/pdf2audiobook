<#
.SYNOPSIS
    启动 PDF 转语音全套服务：qwen-tts-webui + 应用后端 + 前端（已运行的服务自动跳过）。
.DESCRIPTION
    默认启动全部三个服务；可用 -Qwen/-Backend/-Frontend 精确控制；-Stop 改为按端口停止。
.PARAMETER Qwen
    启动/检查 qwen-tts-webui（默认 true）
.PARAMETER Backend
    启动/检查应用后端（默认 true）
.PARAMETER Frontend
    启动/检查前端（默认 true）
.PARAMETER QwenDir
    qwen-tts-webui 所在目录（默认 D:\WorkSpace\qwen-tts-webui）
.PARAMETER Stop
    停止指定服务（按端口），默认停止全部三个
.EXAMPLE
    .\scripts\start-all.ps1
    .\scripts\start-all.ps1 -Frontend
    .\scripts\start-all.ps1 -Stop
#>
param(
    [switch]$Qwen = $true,
    [switch]$Backend = $true,
    [switch]$Frontend = $true,
    [string]$QwenDir = 'D:\WorkSpace\qwen-tts-webui',
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Logs = Join-Path $Root 'data\logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

function Test-Port($Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Stop-Port($Port, $Label) {
    $conns = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($conns) {
        $conns | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
        Write-Host ("[$Label] 已停止 (: " + $Port + ")")
    } else {
        Write-Host ("[$Label] 未在运行 (: " + $Port + ")")
    }
}

function Start-Service($Port, $Label, $Proc) {
    if (Test-Port $Port) {
        Write-Host ("[$Label] 已在运行 (: " + $Port + ")，跳过")
        return
    }
    $out = Join-Path $Logs ($Label + '.out.log')
    $err = Join-Path $Logs ($Label + '.err.log')
    Remove-Item $out, $err -ErrorAction SilentlyContinue
    $p = Start-Process @Proc -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    Write-Host ("[$Label] 启动中 (PID " + $p.Id + " -> : " + $Port + ")")
}

if ($Stop) {
    if ($Qwen)    { Stop-Port 7860 'qwen-tts-webui' }
    if ($Backend) { Stop-Port 8980 'backend' }
    if ($Frontend){ Stop-Port 5456 'frontend' }
    Write-Host '已停止。'
    exit 0
}

if (-not (Test-Path (Join-Path $QwenDir 'launch.py'))) {
    Write-Warning ("未找到 qwen-tts-webui: " + $QwenDir + " (可用 -QwenDir 指定)")
    $script:Qwen = $false
}

if ($Qwen) {
    Start-Service 7860 'qwen' @{
        FilePath = 'python'
        ArgumentList = @('launch.py','--nowebui','--server-name','0.0.0.0','--server-port','7860','--no-inbrowser')
        WorkingDirectory = $QwenDir
    }
}
if ($Backend) {
    $py = Join-Path $Root 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) {
        Write-Warning ("后端虚拟环境不存在: " + $py + "，请先 cd backend 执行 python -m venv .venv 并 pip install -r requirements.txt")
        $script:Backend = $false
    }
    if ($Backend) {
        Start-Service 8980 'backend' @{
            FilePath = $py
            ArgumentList = @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8980')
            WorkingDirectory = Join-Path $Root 'backend'
        }
    }
}
if ($Frontend) {
    Start-Service 5456 'frontend' @{
        FilePath = 'npm.cmd'
        ArgumentList = @('run','dev')
        WorkingDirectory = Join-Path $Root 'frontend'
    }
}

Write-Host ''
Write-Host '访问地址:'
Write-Host '  前端   http://localhost:5456'
Write-Host '  后端   http://127.0.0.1:8980/docs'
Write-Host '  TTS    http://127.0.0.1:7860/qwenapi/v1/'
Write-Host ('日志目录: ' + $Logs)
Write-Host '停止: .\scripts\start-all.ps1 -Stop'
