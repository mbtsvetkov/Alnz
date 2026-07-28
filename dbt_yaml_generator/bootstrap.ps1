# One-command setup for a machine WITHOUT an existing Python env.
# If you already have your dbt venv, skip this and just:
#   pip install -r dbt_yaml_generator/requirements.txt
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = "$here\.venv\Scripts\python.exe"

Write-Host "Creating venv at $here\.venv ..."
python -m venv "$here\.venv"
& $py -m pip install --upgrade pip
& $py -m pip install -r "$here\requirements-dev.txt"

Write-Host "Running offline tests ..."
& $py -m pytest "$here\tests"
Write-Host "OK — package is working. Next: copy config.example.yml to config.yml and edit it."
