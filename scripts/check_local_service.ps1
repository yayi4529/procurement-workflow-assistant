param([string]$BaseUrl = "http://127.0.0.1:8000")
$ErrorActionPreference = "Stop"
$live = Invoke-RestMethod "$($BaseUrl.TrimEnd('/'))/health/live" -TimeoutSec 10
$ready = Invoke-RestMethod "$($BaseUrl.TrimEnd('/'))/health/ready" -TimeoutSec 10
$null = Invoke-RestMethod "$($BaseUrl.TrimEnd('/'))/openapi.json" -TimeoutSec 10
if ($live.status -ne "ok" -or $ready.backend_mode -ne "fake" -or
    -not $ready.feishu_configured -or $ready.llm_enabled) {
    throw "Local service readiness validation failed"
}
Write-Host "PASS: local service is ready"
