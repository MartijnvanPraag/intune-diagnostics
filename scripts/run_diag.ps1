$env:PYTHONPATH = "$PSScriptRoot\..;$PSScriptRoot\..\backend"
uv run python "$PSScriptRoot/diagnose_scenarios.py"
