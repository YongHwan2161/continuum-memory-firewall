param(
    [Parameter(Mandatory = $true)]
    [string]$Narration,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [string]$Voice = "Microsoft Zira Desktop",

    [ValidateRange(-10, 10)]
    [int]$Rate = -1
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$source = Get-Content -LiteralPath $Narration -Raw
$body = ($source -split "`r?`n" | Where-Object { $_ -notmatch '^\s*#' }) -join "`n"
$segments = @($body -split "(?:`r?`n){2,}" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($segments.Count -ne 9) {
    throw "Expected 9 narration segments, found $($segments.Count)."
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$synthesizer = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $synthesizer.SelectVoice($Voice)
    $synthesizer.Rate = $Rate
    for ($index = 0; $index -lt $segments.Count; $index++) {
        $target = Join-Path $OutputDirectory ("segment-{0:D2}.wav" -f ($index + 1))
        $synthesizer.SetOutputToWaveFile($target)
        $synthesizer.Speak($segments[$index])
        $synthesizer.SetOutputToNull()
        Write-Output $target
    }
}
finally {
    $synthesizer.Dispose()
}
