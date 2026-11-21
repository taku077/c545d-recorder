#Requires -Version 5.1
<#
.SYNOPSIS
Read-only candidate GIO compatibility inventory. No rollout is authorized.
.DESCRIPTION
Does not load or copy DLLs, alter PATH, registry, processes or recorder files,
inspect any credentials, enumerate camera devices, or start a GStreamer process.
Prints fixed numeric flags only. "compatible" never means "install approved".

An already-running recorder is always an explicit STOP condition.
The exact official 1.28.8 SDK reference DLL SHA-256 is required; a different
user-installed 1.28.8.1 DLL will BLOCK until an independent compatibility gate
is demonstrated. Do not override or guess the user's installed GIO hash.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$CandidateDll,
    [Parameter(Mandatory=$true)][string]$ManifestFile,
    [Parameter(Mandatory=$true)][string]$GStreamerBin
)
$ErrorActionPreference='Stop'

function Is-X64Pe([string]$file) {
    if(-not (Test-Path -LiteralPath $file -PathType Leaf)){return $false}
    $stream=$null
    $reader=$null
    try {
        $stream=[System.IO.File]::Open($file,[System.IO.FileMode]::Open,
                                      [System.IO.FileAccess]::Read,
                                      [System.IO.FileShare]::ReadWrite)
        if($stream.Length -lt 256){return $false}
        $reader=New-Object System.IO.BinaryReader($stream)
        if($reader.ReadUInt16() -ne 0x5a4d){return $false}
        $stream.Position=0x3c
        $peOffset=$reader.ReadInt32()
        if($peOffset -lt 64 -or $peOffset -gt ($stream.Length - 24)){return $false}
        $stream.Position=$peOffset
        if($reader.ReadUInt32() -ne 0x00004550){return $false}
        return ($reader.ReadUInt16() -eq 0x8664)
    } catch {
        return $false
    } finally {
        if($reader){$reader.Dispose()}
        elseif($stream){$stream.Dispose()}
    }
}

function ManifestHash([string]$body,[string]$key) {
    $match=[regex]::Matches($body,"(?m)^"+[regex]::Escape($key)+"=([a-fA-F0-9]{64})\r?$")
    if($match.Count -ne 1){return ''}
    return $match[0].Groups[1].Value.ToUpperInvariant()
}

# All values printed are fixed booleans and known nonsensitive identifiers.
# Never print runtime paths, package inventory, process command lines,
# exception messages, or the user's local GIO SHA.
$hasFiles=0
$candidateShaOk=0
$referenceShaOk=0
$pe64Ok=0
$runtimeExeOk=0
$activeRecorder=1
$win10=0
$manifestNotForInstall=0
$compatible=0
$reason='INCOMPLETE'
try {
    $baseDll=Join-Path $GStreamerBin 'gio-2.0-0.dll'
    $launcher=Join-Path $GStreamerBin 'gst-launch-1.0.exe'
    $inspector=Join-Path $GStreamerBin 'gst-inspect-1.0.exe'
    $runtimeExeOk=if((Test-Path -LiteralPath $launcher -PathType Leaf) -and
                     (Test-Path -LiteralPath $inspector -PathType Leaf)){1}else{0}
    $hasFiles=if((Test-Path -LiteralPath $CandidateDll -PathType Leaf) -and
                 (Test-Path -LiteralPath $ManifestFile -PathType Leaf) -and
                 (Test-Path -LiteralPath $baseDll -PathType Leaf)){1}else{0}
    if($hasFiles -eq 1){
        $manifest=[System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $ManifestFile).Path)
        $candidateExpected=ManifestHash $manifest 'CANDIDATE_GIO_SHA256'
        $referenceExpected=ManifestHash $manifest 'REFERENCE_GIO_SHA256'
        $manifestNotForInstall=if($manifest -match '(?m)^C545D_RELEASE_CANDIDATE_STATUS=CI_TEST_ONLY_NOT_APPROVED_FOR_HOST\r?$'){1}else{0}
        $actualCandidate=(Get-FileHash -LiteralPath $CandidateDll -Algorithm SHA256).Hash.ToUpperInvariant()
        $actualReference=(Get-FileHash -LiteralPath $baseDll -Algorithm SHA256).Hash.ToUpperInvariant()
        $candidateShaOk=if($candidateExpected.Length -eq 64 -and
                           $actualCandidate -eq $candidateExpected -and
                           $candidateExpected -eq '67B9F7246E4744FEF7EE1EAD3BED4CE2179C6F0465EC68A92D01DD12B4A3CCAD'){1}else{0}
        $referenceShaOk=if($referenceExpected.Length -eq 64 -and
                           $referenceExpected -eq $actualReference -and
                           $referenceExpected -eq 'A875107C180FB248236D1E96E14F362F117124DF2FEE1237FA2142B7B363941B'){1}else{0}
        $pe64Ok=if(Is-X64Pe $CandidateDll){1}else{0}
    }
    $running=@(Get-Process -Name 'gst-launch-1.0','C545D_Recorder' -ErrorAction SilentlyContinue)
    $activeRecorder=if($running.Count -gt 0){1}else{0}
    $os=Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue
    $win10=if($os -and $os.ProductType -eq 1 -and $os.Caption -match 'Windows 10'){1}else{0}
    $compatible=if($hasFiles -eq 1 -and $runtimeExeOk -eq 1 -and
                   $manifestNotForInstall -eq 1 -and $candidateShaOk -eq 1 -and
                   $referenceShaOk -eq 1 -and $pe64Ok -eq 1){1}else{0}
    if($hasFiles -ne 1){$reason='MISSING_INPUT'}
    elseif($candidateShaOk -ne 1 -or $pe64Ok -ne 1){$reason='BAD_CANDIDATE'}
    elseif($referenceShaOk -ne 1){$reason='UNKNOWN_INSTALLED_RUNTIME'}
    elseif($runtimeExeOk -ne 1){$reason='RUNTIME_EXECUTABLE_MISSING'}
    elseif($manifestNotForInstall -ne 1){$reason='PROVENANCE_MISSING'}
    elseif($activeRecorder -ne 0){$reason='RECORDER_ACTIVE'}
    elseif($win10 -ne 1){$reason='WIN10_NOT_VERIFIED'}
    else{$reason='READ_ONLY_COMPATIBILITY_ONLY'}
} catch {
    # Fail closed. Do not include paths, Win32 exception messages or
    # process metadata in diagnostic output.
    $reason='INPUT_READ_ERROR'
}

$eligible=if($compatible -eq 1 -and $activeRecorder -eq 0 -and $win10 -eq 1){1}else{0}
$result=("C545D_CORE_GIO_PREFLIGHT,inputs={0},candidate_sha={1},reference_sha={2},"+
         "pe_x64={3},runtime_exes={4},active_recorder={5},windows10={6},"+
         "compatible={7},read_only_eligibility={8},install_approved=0,reason={9}") -f @(
         $hasFiles,$candidateShaOk,$referenceShaOk,$pe64Ok,$runtimeExeOk,
         $activeRecorder,$win10,$compatible,$eligible,$reason
     )
Write-Output $result
# Never install anything. Even eligible=1 is only a green light for a
# separately controlled smoke test with explicit user approval.
if($eligible -eq 1){exit 0}
exit 3
