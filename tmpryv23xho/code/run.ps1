#requires -Version 5.1
<#
.SYNOPSIS
    Launch AIDeskPal-SICK from a local checkout.
.DESCRIPTION
    Creates .venv on first use (Python 3.11+), installs the package in editable mode,
    then starts the desktop companion. Use -NoInstall to skip dependency checks.
#>
[CmdletBinding()]
param(
    [switch]$NoInstall,
    [string]$Model,
    [switch]$Console
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv venv --python 3.13 .venv
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            py -3.13 -m venv .venv
        } catch {
            py -3 -m venv .venv
        }
    } else {
        python -m venv .venv
    }
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not $NoInstall) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv pip install --python $python -q -e ".[dev]"
    } else {
        & $python -m pip install --disable-pip-version-check -q -e ".[dev]"
    }
}

$launchArgs = @("-m", "aideskpal")
if ($Model) { $launchArgs += @("--model", $Model) }
if (-not $Console) {
    # pythonw keeps the console hidden; logs still go to the app data folder.
    $pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
    if (Test-Path $pythonw) {
        Start-Process -FilePath $pythonw -ArgumentList $launchArgs -WorkingDirectory $root
        return
    }
}
& $python @launchArgs
