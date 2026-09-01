<#
.SYNOPSIS
    停止 PDF 转语音服务（qwen-tts-webui 7860 / 后端 8000 / 前端 5173）。
#>
& (Join-Path $PSScriptRoot 'start-all.ps1') -Stop
