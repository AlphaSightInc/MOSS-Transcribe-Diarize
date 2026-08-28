$ErrorActionPreference = 'Stop'
$null = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/v1/models' -TimeoutSec 10
try {
    $response = Invoke-WebRequest -Uri 'https://127.0.0.1:7861/' -MaximumRedirection 0 -TimeoutSec 10
} catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 303) { throw }
}
$legacy = Test-NetConnection -ComputerName 127.0.0.1 -Port 7860 -InformationLevel Quiet
if ($legacy) { throw 'Legacy plaintext port 7860 is still reachable.' }
Write-Output 'MOSS Account product smoke passed: TLS root reachable; plaintext legacy listener absent.'
