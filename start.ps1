param([string]$Python = 'python', [switch]$Demo, [int]$Port = 8098)
$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
$venvPython = Join-Path $project '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) { $Python = $venvPython }
$dataFolder = Join-Path $project $(if ($Demo) { '.demo-data' } else { '.dev-data' })
$launchArgs = @('-m','app.server','--data',$dataFolder,'--port',"$Port",'--open-browser')
if ($Demo) { $launchArgs += '--demo' }
Push-Location (Join-Path $project 'cookeo')
try { & $Python @launchArgs } finally { Pop-Location }
