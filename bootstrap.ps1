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

$root = (Resolve-Path $PSScriptRoot).Path
$venv = Join-Path $root ".venv"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    & $python -m venv $venv
}

$venvPython = Join-Path $venv "Scripts\python.exe"

# Windows cannot replace a console-script executable while it is running. Make
# this an explicit, actionable prerequisite instead of allowing pip to leave a
# partially upgraded environment while the bootstrap script reports success.
$venvRift = Join-Path $venv "Scripts\rift.exe"
$runningRift = Get-Process -Name "rift" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and ((Resolve-Path $_.Path).Path -eq (Resolve-Path $venvRift).Path) }
if ($runningRift) {
    throw "RIFT is currently running from $venvRift. Stop the controller/dashboard and run bootstrap.ps1 again."
}

# Recover the temporary names pip leaves behind after an interrupted Windows
# script replacement (for example, ``~ift`` and ``~ift_llm-*.dist-info``).
$sitePackages = Join-Path $venv "Lib\site-packages"
Get-ChildItem -LiteralPath $sitePackages -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "~ift*" } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install --upgrade setuptools wheel packaging
& $venvPython -m pip install --no-cache-dir $root
if ($LASTEXITCODE -ne 0) {
    throw "RIFT installation failed. No success state was reported."
}

Write-Host "RIFT is ready."
Write-Host "Start it with: .\.venv\Scripts\rift.exe start"
