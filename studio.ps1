param(
    [Parameter(Position = 0)]
    [ValidateSet("setup", "smoke", "validate", "radio", "film", "regen", "test", "clean", "help")]
    [string]$Cmd = "help",

    [Parameter(Position = 1)]
    [string]$Shot = "s03",

    [Parameter(Position = 2)]
    [string]$Stage = "keyframes"
)

$ErrorActionPreference = "Stop"
$Py = ".\.venv\Scripts\python.exe"

switch ($Cmd) {
    "setup" {
        python -m venv .venv
        & $Py -m pip install --upgrade pip -q
        & $Py -m pip install -r requirements.txt
    }
    "smoke"    { & $Py heritage_studio.py smoke }
    "validate" { & $Py heritage_studio.py validate }
    "radio"    { & $Py heritage_studio.py radio }
    "film"     { & $Py heritage_studio.py run }
    "regen"    {
        & $Py heritage_studio.py regen --stage $Stage --shot $Shot
        & $Py heritage_studio.py run
    }
    "test"     { & $Py -m pytest -v }
    "clean"    { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue outputs, runs.jsonl }
    default {
        Write-Host "Usage: .\studio.ps1 <command>"
        Write-Host "  setup     Create .venv and install dependencies"
        Write-Host "  smoke     Check keys, FFmpeg, and log to runs.jsonl"
        Write-Host "  validate  Validate storyboard.json against schema"
        Write-Host "  radio     Build Phase 1 animated radio cut (portrait + full audio)"
        Write-Host "  film      Build full 9:16 and 16:9 films"
        Write-Host "  regen     Regenerate one shot (default: s03 keyframes) & re-assemble"
        Write-Host "  test      Run pytest suite"
        Write-Host "  clean     Remove outputs/ and runs.jsonl"
    }
}
