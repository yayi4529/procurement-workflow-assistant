param([Parameter(Mandatory = $true)][string]$BaseUrl)
$ErrorActionPreference = "Stop"
$uri = [Uri]$BaseUrl
if ($uri.Scheme -ne "https") { throw "BaseUrl must use HTTPS" }
$result = Invoke-RestMethod "$($BaseUrl.TrimEnd('/'))/health/live" -TimeoutSec 15
if ($result.status -ne "ok") { throw "Public health check failed" }
Write-Host "PASS: public HTTPS service is reachable"
Write-Host "$($BaseUrl.TrimEnd('/'))/webhooks/feishu"
Write-Host "$($BaseUrl.TrimEnd('/'))/internal/notifications"
