#Requires -Version 5.1
<#
Read-only core GIO dependency fingerprint. Never loads or changes a DLL,
recorder, camera, registry, PATH or user files. Output is numeric-only.
PASS is never authorization to install a DLL on the recording PC.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$GStreamerBin,
  [Parameter(Mandatory=$true)][string]$ReferenceManifest,
  [Parameter(Mandatory=$true)][string]$CandidateDll
)
$ErrorActionPreference='Stop'
$names=@('gio-2.0-0.dll','glib-2.0-0.dll','gobject-2.0-0.dll',
         'gmodule-2.0-0.dll','intl-8.dll','z-1.dll')
$referenceGio='A875107C180FB248236D1E96E14F362F117124DF2FEE1237FA2142B7B363941B'
$referenceCandidate='67B9F7246E4744FEF7EE1EAD3BED4CE2179C6F0465EC68A92D01DD12B4A3CCAD'
$found=0;$matched=0;$x64=0;$missing=0;$mismatch=0;$invalid=0
$candidateValid=0;$manifestValid=0;$reason='UNREADABLE_INPUT'
function Test-X64Pe([string]$file) {
  $stream=$null;$reader=$null
  try {
    $stream=[IO.File]::Open($file,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
    if($stream.Length -lt 256){return $false}
    $reader=New-Object IO.BinaryReader($stream)
    if($reader.ReadUInt16() -ne 0x5A4D){return $false}
    $stream.Position=0x3c
    $offset=$reader.ReadInt32()
    if($offset -lt 64 -or $offset -gt ($stream.Length-24)){return $false}
    $stream.Position=$offset
    return ($reader.ReadUInt32() -eq 0x4550 -and $reader.ReadUInt16() -eq 0x8664)
  } catch {return $false}
  finally {if($reader){$reader.Dispose()}elseif($stream){$stream.Dispose()}}
}
try {
  $m=Get-Content -LiteralPath $ReferenceManifest -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
  $props=@($m.dll_sha256.PSObject.Properties.Name)
  $gioExpected=[string]$m.dll_sha256.PSObject.Properties['gio-2.0-0.dll'].Value
  if($m.schema -ne 1 -or
     $m.sdk -ne 'gstreamer-1.0-msvc-x86_64-1.28.8' -or
     $m.install_approved -ne $false -or
     ([string]$m.candidate_sha256).ToUpperInvariant() -ne $referenceCandidate -or
     $props.Count -ne $names.Count -or
     @($props | Where-Object {$_ -cnotin $names}).Count -ne 0 -or
     $gioExpected.ToUpperInvariant() -ne $referenceGio){throw 'bad fixed-source manifest'}
  foreach($name in $names){
    $value=[string]$m.dll_sha256.PSObject.Properties[$name].Value
    if($value -notmatch '^[A-Fa-f0-9]{64}$'){throw 'bad digest'}
  }
  $manifestValid=1
  foreach($name in $names){
    $dll=Join-Path $GStreamerBin $name
    if(-not (Test-Path -LiteralPath $dll -PathType Leaf)){$missing++;continue}
    $found++
    $item=Get-Item -LiteralPath $dll
    if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){$invalid++;continue}
    $expected=([string]$m.dll_sha256.PSObject.Properties[$name].Value).ToUpperInvariant()
    $actual=(Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash
    if($actual -eq $expected){$matched++}else{$mismatch++}
    if(Test-X64Pe $dll){$x64++}else{$invalid++}
  }
  if((Test-Path -LiteralPath $CandidateDll -PathType Leaf) -and
     (Get-FileHash -LiteralPath $CandidateDll -Algorithm SHA256).Hash -eq $referenceCandidate -and
     (Test-X64Pe $CandidateDll)){$candidateValid=1}
  if($missing){$reason='MISSING_CORE_DLL'}
  elseif($mismatch){$reason='UNKNOWN_RUNTIME_DLL_HASH'}
  elseif($invalid){$reason='INVALID_CORE_DLL_PE'}
  elseif(-not $candidateValid){$reason='BAD_CANDIDATE'}
  else{$reason='READ_ONLY_GRAPH_MATCH'}
} catch {
  # No exception message/paths/unknown host file hash are ever revealed.
  $reason='INVALID_REFERENCE_MANIFEST'
}
$match=[int]($manifestValid -eq 1 -and $found -eq 6 -and $matched -eq 6 -and
             $x64 -eq 6 -and $missing -eq 0 -and $mismatch -eq 0 -and
             $invalid -eq 0 -and $candidateValid -eq 1)
$line=('C545D_GIO_CORE_GRAPH_PREFLIGHT,manifest_valid={0},core_found={1},core_hash_matched={2},'+
       'core_pe_x64={3},missing={4},hash_mismatch={5},invalid_pe={6},candidate_valid={7},'+
       'graph_match={8},install_approved=0,reason={9}') -f
      $manifestValid,$found,$matched,$x64,$missing,$mismatch,$invalid,$candidateValid,$match,$reason
Write-Output $line
if($match){exit 0}
exit 3
