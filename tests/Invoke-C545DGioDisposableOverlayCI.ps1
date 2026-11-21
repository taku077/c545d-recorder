#Requires -Version 5.1
<#
CI ONLY. An app-local GIO overlay proof with strict disposable ownership.
Never run this on a recorder PC. It never changes an installed SDK DLL.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SdkRoot,
  [Parameter(Mandatory=$true)][string]$CandidateDll,
  [Parameter(Mandatory=$true)][string]$CandidateManifest,
  [Parameter(Mandatory=$true)][string]$ReferenceManifest,
  [Parameter(Mandatory=$true)][string]$ScratchRoot
)
$ErrorActionPreference='Stop'
$reason='INPUT_REJECTED'
$verified=0;$deleted=0;$owned=$false;$stage=$null
$rcSha='67B9F7246E4744FEF7EE1EAD3BED4CE2179C6F0465EC68A92D01DD12B4A3CCAD'
$sdkSha='A875107C180FB248236D1E96E14F362F117124DF2FEE1237FA2142B7B363941B'
try {
  if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows' -or
     -not $env:RUNNER_TEMP){throw 'CI_ONLY'}
  $temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
  $stage=[IO.Path]::GetFullPath($ScratchRoot).TrimEnd('\')
  if(-not [string]::Equals([IO.Path]::GetDirectoryName($stage).TrimEnd('\'),$temp,[StringComparison]::OrdinalIgnoreCase) -or
     [IO.Path]::GetFileName($stage) -cnotmatch '^c545d-ci-owned-overlay-[A-Za-z0-9]{6,32}$' -or
     (Test-Path -LiteralPath $stage)){throw 'INVALID_STAGE_PATH'}
  $ref=Get-Content -LiteralPath $ReferenceManifest -Raw | ConvertFrom-Json
  if($ref.sdk -ne 'gstreamer-1.0-msvc-x86_64-1.28.8' -or $ref.schema -ne 1 -or
     $ref.install_approved -ne $false -or
     ([string]$ref.candidate_sha256).ToUpperInvariant() -ne $rcSha){throw 'BAD_REFERENCE'}
  $names=@('gio-2.0-0.dll','glib-2.0-0.dll','gobject-2.0-0.dll',
           'gmodule-2.0-0.dll','intl-8.dll','z-1.dll')
  if(@($ref.dll_sha256.PSObject.Properties.Name).Count -ne 6){throw 'BAD_REFERENCE'}
  $sdkBin=Join-Path $SdkRoot 'bin'
  foreach($name in $names) {
    $f=Join-Path $sdkBin $name
    $expected=([string]$ref.dll_sha256.PSObject.Properties[$name].Value).ToUpperInvariant()
    if($expected -notmatch '^[A-F0-9]{64}$' -or
       -not (Test-Path -LiteralPath $f -PathType Leaf) -or
       (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash -ne $expected){
       throw 'SDK_NOT_PINNED'
    }
  }
  $manifest=[IO.File]::ReadAllText((Resolve-Path -LiteralPath $CandidateManifest).Path)
  if(-not (Test-Path -LiteralPath $CandidateDll -PathType Leaf) -or
     (Get-FileHash -LiteralPath $CandidateDll -Algorithm SHA256).Hash -ne $rcSha -or
     $manifest -notmatch ('(?m)^CANDIDATE_GIO_SHA256='+$rcSha+'\r?$') -or
     $manifest -notmatch ('(?m)^REFERENCE_GIO_SHA256='+$sdkSha+'\r?$') -or
     $manifest -notmatch '(?m)^C545D_RELEASE_CANDIDATE_STATUS=CI_TEST_ONLY_NOT_APPROVED_FOR_HOST\r?$'){
    throw 'CANDIDATE_NOT_PINNED'
  }
  $test=Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'Assert-C545DGioProcessLoaderCI.ps1'
  $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  if(-not (Test-Path -LiteralPath $test -PathType Leaf) -or -not (Test-Path -LiteralPath $ps -PathType Leaf)){
    throw 'CHECKER_NOT_AVAILABLE'
  }
  New-Item -ItemType Directory -Path $stage -Force | Out-Null
  $marker=Join-Path $stage '.c545d-ci-owned'
  [IO.File]::WriteAllText($marker,'C545D_CI_OWNED_ISOLATED_GIO_TEST')
  $owned=$true
  $lines=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $test -SdkRoot $SdkRoot -CandidateDll $CandidateDll -WorkRoot $stage 2>$null)
  $childExit=$LASTEXITCODE
  if($childExit -ne 0 -or $lines.Count -ne 3){throw 'CHILD_NOT_QUALIFIED'}
  $expected=@(
    'C545D_GIO_LOADER_OBSERVATION,mode=installed,module_expected=1,output_valid=1,process_exit=0,CI_only=1',
    'C545D_GIO_LOADER_OBSERVATION,mode=isolated,module_expected=1,output_valid=1,process_exit=0,CI_only=1',
    'C545D_GIO_REAL_PROCESS_LOADER_CI_PASS,installed_exe_uses_official=1,PATH_override_did_not_bypass_app_dir=1,isolated_exe_uses_candidate=1,live_module_path_confirmed=1,original_sdk_unchanged=1,synthetic_GIO_audio_write=1,recorder_host_modified=0'
  )
  if(@($lines | Where-Object {$_ -cnotin $expected}).Count -ne 0 -or
     @($expected | Where-Object {$_ -cnotin $lines}).Count -ne 0){throw 'MISSING_DLL_PROOF'}
  foreach($wav in @('installed.wav','isolated.wav')){
    $p=Join-Path $stage $wav
    if(-not (Test-Path -LiteralPath $p -PathType Leaf) -or
       (Get-Item -LiteralPath $p).Length -lt 30000){throw 'MISSING_GIO_WAV'}
  }
  if((Get-FileHash -LiteralPath $CandidateDll -Algorithm SHA256).Hash -ne $rcSha -or
     (Get-FileHash -LiteralPath (Join-Path $sdkBin 'gio-2.0-0.dll') -Algorithm SHA256).Hash -ne $sdkSha){
    throw 'INPUT_MUTATED'
  }
  $verified=1
  $reason='QUALIFIED'
} catch {
  # Never print OS paths, child stderr, local hashes or exception content.
  $reason='BLOCKED'
} finally {
  if($owned){
    try{
      $item=Get-Item -LiteralPath $stage -Force -ErrorAction Stop
      if($item.PSIsContainer -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 -and
         [IO.File]::ReadAllText((Join-Path $stage '.c545d-ci-owned')) -ceq 'C545D_CI_OWNED_ISOLATED_GIO_TEST'){
        $alive=@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue | Where-Object {
          $_.Path -and $_.Path.StartsWith(($stage+'\'),[StringComparison]::OrdinalIgnoreCase)
        })
        if($alive.Count -eq 0){
          Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction Stop
          $deleted=[int](-not (Test-Path -LiteralPath $stage))
        }
      }
    }catch{$deleted=0}
  } else {
    $deleted=[int](-not (Test-Path -LiteralPath $stage))
  }
}
if($verified -eq 1 -and $deleted -eq 1){$reason='ISOLATION_AND_ROLLBACK_PASS'}
else{$verified=0}
Write-Output "C545D_DISPOSABLE_GIO_CI,module_paths_verified=$verified,rollback_deleted=$deleted,host_modified=0,install_approved=0,reason=$reason"
if($verified -eq 1 -and $deleted -eq 1){exit 0}
exit 3
