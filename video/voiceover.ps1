# Offline narration with the Windows speech engine: one WAV per line of narration.json in build/.
# build.mjs measures each WAV and places it at the line's "start" time; spelling in narration.json
# is phonetic where the voice needs help ("Dream Guard", "D P D P").
# Voice: set DG_VOICE (e.g. "Microsoft David Desktop") to change it. Run: npm run voiceover
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$lines = (Get-Content (Join-Path $PSScriptRoot "narration.json") -Raw -Encoding UTF8 | ConvertFrom-Json) | ForEach-Object { $_.text }
$out = Join-Path $PSScriptRoot "build"
New-Item -ItemType Directory -Force $out | Out-Null
$voice = if ($env:DG_VOICE) { $env:DG_VOICE } else { "Microsoft Zira Desktop" }
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)

for ($i = 0; $i -lt $lines.Count; $i++) {
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice($voice)
  $s.Rate = 0
  $file = Join-Path $out ("vo_{0:D2}.wav" -f $i)
  $s.SetOutputToWaveFile($file, $format)
  $s.Speak($lines[$i])
  $s.Dispose()
  Write-Output "wrote $file"
}
