param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$launcher = Get-Command py.exe -ErrorAction SilentlyContinue

if ($null -eq $launcher) {
    Write-Error "The Windows Python launcher (py.exe) was not found. Install CPython 3.12, then rerun this script."
    exit 1
}

& $launcher.Source -3.12 -c "import platform, sys; assert sys.version_info[:2] == (3, 12); assert platform.python_implementation() == 'CPython'; assert sys.maxsize > 2**32"
if ($LASTEXITCODE -ne 0) {
    Write-Host "CPython 3.12 is required and was not found."
    Write-Host "Safe per-user install command:"
    Write-Host "winget install --exact --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements"
    exit 1
}

Set-Location -LiteralPath $projectRoot
$environment = Join-Path $projectRoot ".venv"
$projectPython = Join-Path $environment "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $projectPython)) {
    if (Test-Path -LiteralPath $environment) {
        throw ".venv exists but is not a usable Windows virtual environment. Remove only that project-local directory and rerun."
    }
    & $launcher.Source -3.12 -m venv $environment
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python 3.12 virtual environment." }
}

& $projectPython -c "import platform, sys; assert sys.version_info[:2] == (3, 12); assert platform.python_implementation() == 'CPython'; assert sys.maxsize > 2**32"
if ($LASTEXITCODE -ne 0) {
    throw ".venv does not use Python 3.12. Remove only the project-local .venv directory and rerun."
}

& $projectPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip in .venv." }
& $projectPython -m pip install -e . -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Could not install project dependencies in .venv." }
& $projectPython scripts/validate_python_runtime.py
if ($LASTEXITCODE -ne 0) { throw "Python runtime validation failed." }

Write-Host "Commander Arena is ready. Start it without opening a browser:"
Write-Host ".\.venv\Scripts\python.exe -m server --no-open"
