param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
& $Python -m venv (Join-Path $PSScriptRoot '.venv')
if ($LASTEXITCODE -ne 0) { throw 'Je potřeba Python 3.12 nebo novější.' }
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -m pip install -r (Join-Path $PSScriptRoot 'cookeo\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Instalace závislostí se nezdařila.' }
