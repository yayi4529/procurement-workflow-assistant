param(
    [Parameter(Mandatory = $true)][string]$BaseUrl,
    [Parameter(Mandatory = $true)][string]$ReceiverOpenId
)
$ErrorActionPreference = "Stop"
$notificationId = Get-Random -Minimum 100000 -Maximum 2000000000
$dedupKey = "dev-smoke-$([Guid]::NewGuid())"
python "$PSScriptRoot/send_test_notification.py" --base-url $BaseUrl --receiver-open-id $ReceiverOpenId --requirement-id 1 --requirement-no "DEV-SMOKE-001" --notification-id $notificationId --dedup-key $dedupKey --mode send
python "$PSScriptRoot/send_test_notification.py" --base-url $BaseUrl --receiver-open-id $ReceiverOpenId --requirement-id 1 --requirement-no "DEV-SMOKE-001" --notification-id $notificationId --dedup-key $dedupKey --mode duplicate
python "$PSScriptRoot/send_test_notification.py" --base-url $BaseUrl --receiver-open-id $ReceiverOpenId --requirement-id 1 --requirement-no "DEV-SMOKE-001" --notification-id $notificationId --dedup-key $dedupKey --mode conflict
python "$PSScriptRoot/send_test_notification.py" --base-url $BaseUrl --receiver-open-id $ReceiverOpenId --requirement-id 1 --requirement-no "DEV-SMOKE-001" --mode unauthorized
Write-Host "PASS: notification smoke modes completed"
