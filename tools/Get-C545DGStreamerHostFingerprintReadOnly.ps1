#Requires -Version 5.1
<#
.SYNOPSIS
Read-only, no-stop GStreamer MSVC core DLL inventory for a future one-time host check.
.DESCRIPTION
Does not launch/stop GStreamer, load/replace DLLs, change PATH or registry,
read Tapo credentials, create files, or make network calls. Safe to run while
a recorder is active. Prints ONE numeric line, never a local file path or
a private host file digest. Checks only the six official 1.28.8 reference DLLs,
NOT the complete transitive CRT/API-set graph or a live RTSP session.
#>
[CmdletBinding()]
param(
  [string]$GStreamerBin = '',
  [string]$ReferenceManifest = ''
)
$ErrorActionPreference='Stop'
$filesFound=0;$matched=0;$missing=0;$notPe64=0
$runtimeFound=0;$runtimeExe=0;$os10=0;$recordingActive=0;$manifestValid=0
$reason='INCOMPLETE'
try {
  if(-not $ReferenceManifest){
    $here=Split-Path -Parent $MyInvocation.MyCommand.Path
    $adjacent=Join-Path $here 'CORE_GIO_SDK_1288_REFERENCE.json'
    $inRepo=Join-Path (Split-Path -Parent $here) 'docs\CORE_GIO_SDK_1288_REFERENCE.json'
    if(Test-Path -LiteralPath $adjacent -PathType Leaf){$ReferenceManifest=$adjacent}
    else{$ReferenceManifest=$inRepo}
  }
  $ref=Get-Content -LiteralPath $ReferenceManifest -Raw | ConvertFrom-Json
  $names=@('gio-2.0-0.dll','glib-2.0-0.dll','gobject-2.0-0.dll',
           'gmodule-2.0-0.dll','intl-8.dll','z-1.dll')
  if($ref.schema -ne 1 -or $ref.install_approved -ne $false -or
     $ref.sdk -ne 'gstreamer-1.0-msvc-x86_64-1.28.8' -or
     @($ref.dll_sha256.PSObject.Properties.Name).Count -ne 6 -or
     ([string]$ref.dll_sha256.PSObject.Properties['gio-2.0-0.dll'].Value).ToUpperInvariant() -ne 'A875107C180FB248236D1E96E14F362F117124DF2FEE1237FA2142B7B363941B'){
    throw 'bad pinned public reference'
  }
  foreach($name in $names){
    $hash=([string]$ref.dll_sha256.PSObject.Properties[$name].Value).ToUpperInvariant()
    if($hash -notmatch '^[A-F0-9]{64}$'){throw 'bad public SHA'}
  }
  $manifestValid=1

  if(-not $GStreamerBin){
    # Match the exact install-directory selection precedence in Record.ps1.
    $locations=@(
      (Join-Path $env:LOCALAPPDATA 'Programs\gstreamer\1.0\msvc_x86_64\bin'),
      (Join-Path $env:ProgramFiles 'gstreamer\1.0\msvc_x86_64\bin'),
      'C:\gstreamer\1.0\msvc_x86_64\bin'
    )
    foreach($location in $locations){
      if($location -and (Test-Path -LiteralPath (Join-Path $location 'gst-launch-1.0.exe') -PathType Leaf)){
        $GStreamerBin=$location
        break
      }
    }
    if(-not $GStreamerBin){
      $exe=Get-Command -Name gst-launch-1.0.exe -ErrorAction SilentlyContinue
      if($exe){$GStreamerBin=Split-Path -Parent $exe.Source}
    }
  }
  if($GStreamerBin -and (Test-Path -LiteralPath $GStreamerBin -PathType Container)){
    $runtimeFound=1
    if((Test-Path -LiteralPath (Join-Path $GStreamerBin 'gst-launch-1.0.exe') -PathType Leaf) -and
       (Test-Path -LiteralPath (Join-Path $GStreamerBin 'gst-inspect-1.0.exe') -PathType Leaf)){
      $runtimeExe=1
    }
    foreach($name in $names){
      $file=Join-Path $GStreamerBin $name
      if(-not (Test-Path -LiteralPath $file -PathType Leaf)){$missing++;continue}
      $filesFound++
      $info=Get-Item -LiteralPath $file
      if(($info.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){
        $notPe64++
        continue
      }
      $expected=([string]$ref.dll_sha256.PSObject.Properties[$name].Value).ToUpperInvariant()
      $actual=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
      if($actual -eq $expected){$matched++}
      $s=$null;$r=$null
      try {
        $s=[IO.File]::Open($file,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
        $r=New-Object IO.BinaryReader($s)
        if($s.Length -lt 256 -or $r.ReadUInt16() -ne 0x5A4D){$notPe64++;continue}
        $s.Position=0x3c
        $offset=$r.ReadInt32()
        if($offset -lt 64 -or $offset -gt ($s.Length - 24)){
          $notPe64++
          continue
        }
        $s.Position=$offset
        if($r.ReadUInt32() -ne 0x4550 -or $r.ReadUInt16() -ne 0x8664){$notPe64++}
      } finally {
        if($r){$r.Dispose()}elseif($s){$s.Dispose()}
      }
    }
  }
  $os=Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
  $os10=[int]($os -and $os.ProductType -eq 1 -and $os.Caption -match 'Windows 10')
  $running=@(Get-Process -Name 'gst-launch-1.0','C545D_Recorder' -ErrorAction SilentlyContinue)
  $recordingActive=[int]($running.Count -gt 0)
  if($runtimeFound -eq 0){$reason='GSTREAMER_NOT_FOUND'}
  elseif($runtimeExe -eq 0){$reason='GSTREAMER_EXE_MISSING'}
  elseif($missing -gt 0){$reason='SOME_DLLS_MISSING'}
  elseif($notPe64 -gt 0){$reason='PE_X64_NOT_PROVEN'}
  elseif($matched -lt 6){$reason='INSTALLED_RUNTIME_DIFFERS_FROM_PINNED_1288'}
  elseif($os10 -eq 0){$reason='PINNED_SDK_MATCH_NON_WIN10'}
  else{$reason='PINNED_SDK_HASH_MATCH_READ_ONLY'}
} catch {
  # Never put a host path, SHA, credential, or exception into stdout.
  $reason='READ_ONLY_CHECK_INCOMPLETE'
}
$match=[int]($runtimeExe -eq 1 -and $filesFound -eq 6 -and $matched -eq 6 -and
             $missing -eq 0 -and $notPe64 -eq 0 -and $manifestValid -eq 1)
$line=("C545D_HOST_GIO_FINGERPRINT,manifest_valid={0},runtime_found={1},"+
       "executables_found={2},dll_found={3},dll_hash_matched={4},"+
       "dll_missing={5},pe64_failed={6},windows10={7},recorder_active={8},"+
       "pinned_sdk_match={9},install_approved=0,live_test_authorized=0,reason={10}") -f @(
        $manifestValid,$runtimeFound,$runtimeExe,$filesFound,$matched,$missing,
        $notPe64,$os10,$recordingActive,$match,$reason)
Write-Output $line
# A DIFFERENT runtime is information, not authorization to change it.
if($match -eq 1){exit 0}
exit 3
