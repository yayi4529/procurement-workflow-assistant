param(
    [ValidateSet("cloudflared", "ngrok")]
    [string]$Provider,
    [string]$LocalUrl = "http://127.0.0.1:8000"
)
$ErrorActionPreference = "Stop"
if (-not (Get-Command $Provider -ErrorAction SilentlyContinue)) {
    throw "$Provider is not installed or not on PATH"
}
if ($Provider -eq "cloudflared") {
    Write-Host "Starting Cloudflare Quick Tunnel for $LocalUrl"
    & cloudflared tunnel --url $LocalUrl
} else {
    Write-Host "Starting ngrok tunnel for $LocalUrl"
    & ngrok http $LocalUrl
}
