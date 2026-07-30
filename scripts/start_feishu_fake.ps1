param(
    [string]$EnvFile = ".env.feishu-fake",
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Resolve-Path -LiteralPath (Join-Path $repoRoot $EnvFile)
python (Join-Path $PSScriptRoot "validate_feishu_fake_config.py") --env-file $envPath
Get-Content -LiteralPath $envPath -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $name, $value = $line.Split("=", 2)
        [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim().Trim("'`""), "Process")
    }
}
Write-Host "Local health: http://127.0.0.1:$Port/health/ready"
Write-Host "Feishu webhook: http://127.0.0.1:$Port$env:PROCUREMENT_FEISHU_WEBHOOK_PATH"
Write-Host "Notification gateway: http://127.0.0.1:$Port$env:PROCUREMENT_NOTIFICATION_GATEWAY_PATH"
Set-Location $repoRoot
$env:PYTHONPATH = Join-Path $repoRoot "src"
python -m uvicorn procurement_platform.interfaces.http.app:create_app --factory --host $HostAddress --port $Port --workers 1
