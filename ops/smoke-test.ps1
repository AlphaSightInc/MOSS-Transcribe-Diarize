$ErrorActionPreference = 'Stop'

$projectDir = 'D:\Coding\MOSS-Transcribe-Diarize'
$runsDir = Join-Path $projectDir 'runs'
$samplePath = Join-Path $runsDir 'smoke-test.wav'
$modelName = 'OpenMOSS-Team/MOSS-Transcribe-Diarize'

New-Item -ItemType Directory -Force -Path $runsDir | Out-Null

$null = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/v1/models' -TimeoutSec 10
$null = Invoke-RestMethod -Uri 'http://127.0.0.1:7860/api/runtime' -TimeoutSec 10

Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SetOutputToWaveFile($samplePath)
    $speaker.Speak('Hello. This is a MOSS transcription test running on the local computer.')
}
finally {
    $speaker.Dispose()
}

$curlArguments = @(
    '--fail-with-body'
    '--silent'
    '--show-error'
    '--max-time', '600'
    '-X', 'POST'
    'http://127.0.0.1:8000/v1/audio/transcriptions'
    '-F', "file=@$samplePath"
    '-F', "model=$modelName"
    '-F', 'response_format=json'
    '-F', 'max_new_tokens=256'
)
$rawResponse = & curl.exe @curlArguments
if ($LASTEXITCODE -ne 0) {
    throw "The transcription request failed with exit code $LASTEXITCODE."
}

$response = $rawResponse | ConvertFrom-Json
if (-not $response.text) {
    throw 'The transcription response did not contain text.'
}

Write-Output "MOSS smoke test passed: $($response.text)"
