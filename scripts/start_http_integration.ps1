param(
    [string]$EnvFile = ".env",
    [string]$BackendBaseUrl = "http://127.0.0.1:8001",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8002,
    [string]$PythonPath = "",
    [switch]$AllowTestPlatform,
    [switch]$EnableLlm
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot $EnvFile
if (Test-Path -LiteralPath $envPath) {
    Get-Content -LiteralPath $envPath -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $name, $value = $line.Split("=", 2)
            [Environment]::SetEnvironmentVariable(
                $name.Trim(),
                $value.Trim().Trim([char]34).Trim([char]39),
                "Process"
            )
        }
    }
}

if (-not $env:PROCUREMENT_IDENTITY_GATEWAY_SECRET) {
    throw "PROCUREMENT_IDENTITY_GATEWAY_SECRET must be set in the current process or $EnvFile before starting HTTP integration."
}

$backendUrl = $BackendBaseUrl.TrimEnd("/")
$backendReady = Invoke-RestMethod "$backendUrl/ready" -TimeoutSec 10
if (-not $backendReady.success -or $backendReady.data.status -ne "ready") {
    throw "Procurement backend is not ready: $backendUrl/ready"
}

if ($PythonPath) {
    $resolvedPython = $PythonPath
} else {
    $localPython312 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path -LiteralPath $localPython312) {
        $resolvedPython = $localPython312
    } else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $pythonCommand) {
            throw "Python was not found. Pass -PythonPath with a Python 3.11+ executable."
        }
        $resolvedPython = $pythonCommand.Source
    }
}

if (-not (Test-Path -LiteralPath $resolvedPython)) {
    throw "Python executable was not found: $resolvedPython"
}

$env:PROCUREMENT_ENVIRONMENT = "development"
$env:PROCUREMENT_BACKEND_MODE = "http"
$env:PROCUREMENT_BACKEND_BASE_URL = $backendUrl
$env:PROCUREMENT_BACKEND_REQUEST_TIMEOUT_SECONDS = "10"
$env:PROCUREMENT_LLM_ENABLED = $EnableLlm.IsPresent.ToString().ToLowerInvariant()
$env:PROCUREMENT_ALLOW_TEST_PLATFORM = $AllowTestPlatform.IsPresent.ToString().ToLowerInvariant()
$env:PYTHONPATH = Join-Path $repoRoot "src"

Write-Host "Procurement backend: $backendUrl"
Write-Host "Agent readiness: http://$HostAddress`:$Port/health/ready"
Write-Host "LLM enabled: $($env:PROCUREMENT_LLM_ENABLED)"
Write-Host "The gateway secret is read only from the current process and is never printed."

Set-Location $repoRoot
& $resolvedPython -m uvicorn procurement_platform.interfaces.http.app:create_app --factory --host $HostAddress --port $Port --workers 1
