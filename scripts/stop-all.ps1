<#
.SYNOPSIS
    停止 PDF 转语音服务（qwen-tts-webui 7860 / 后端 8980 / 前端 5456）。
#>
& (Join-Path $PSScriptRoot 'start-all.ps1') -Stop
