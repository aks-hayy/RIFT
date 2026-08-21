$ErrorActionPreference = "Stop"

function Get-PythonCommand {
    $candidates = @("py", "python")
    foreach ($candidate in $candidates) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }
    throw "Python 3.10 or newer is required. Install Python and run this script again."
}

$python = Get-PythonCommand
$version = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$parts = $version.Split('.')
if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 10)) {
    throw "RIFT requires Python 3.10 or newer; detected $version."
}

$venv = Join-Path (Get-Location) ".venv"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    & $python -m venv $venv
}
$venvPython = Join-Path $venv "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install .

Write-Host "RIFT is ready. Start it with: .\.venv\Scripts\rift.exe start"
