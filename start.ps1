# Start TinyPedal using the project virtual environment
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir
& "$scriptDir\.venv\Scripts\python.exe" "$scriptDir\run.py" @args
