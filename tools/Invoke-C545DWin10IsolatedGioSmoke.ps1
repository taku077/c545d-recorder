#Requires -Version 5.1
<#
DEVELOPMENT ONLY. Future optional camera-free app-local GIO smoke.
Not approved for user Win10 execution, production install, or live Tapo testing.
Never modifies installed DLLs, starts/stops an existing recorder, or reads RTSP.
#>
[CmdletBinding()]
param([string]$GStreamerBin='', [string]$CandidateDll='',
      [string]$CandidateManifest='', [string]$ReferenceManifest='',
      [switch]$CiRunnerOnly)
$ErrorActionPreference='Stop'
$rc='67B9F7246E4744FEF7EE1EAD3BED4CE2179C6F0465EC68A92D01DD12B4A3CCAD'
$sdk='A875107C180FB248236D1E96E14F362F117124DF2FEE1237FA2142B7B363941B'
$started=0;$observed=0;$wav=0;$cleanExit=0;$cleanup=0;$originals=0;$reason='BLOCKED'
$owned=$false;$stage=$null;$child=$null;$childExited=$true;$handle=[IntPtr]::Zero
$prior=@{}
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class C545DHostGioSmokeQuery {
  [DllImport("kernel32.dll",SetLastError=true)] public static extern IntPtr OpenProcess(uint a,bool i,int p);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool GetExitCodeProcess(IntPtr h,out uint c);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool CloseHandle(IntPtr h);
}
'@
try {
  $home=Split-Path -Parent $MyInvocation.MyCommand.Path
  if(-not $CandidateDll){$CandidateDll=Join-Path $home 'gio-2.0-0.dll'}
  if(-not $CandidateManifest){$CandidateManifest=Join-Path $home 'manifest.txt'}
  if(-not $ReferenceManifest){$ReferenceManifest=Join-Path $home 'CORE_GIO_SDK_1288_REFERENCE.json'}
  $check=Join-Path $home 'Get-C545DGStreamerHostFingerprintReadOnly.ps1'
  $isCi=($CiRunnerOnly -and $env:GITHUB_ACTIONS -eq 'true' -and $env:RUNNER_OS -eq 'Windows' -and $env:RUNNER_TEMP)
  if($CiRunnerOnly -and -not $isCi){throw 'NOT_CI'}
  if(-not (Test-Path -LiteralPath $check -PathType Leaf)){throw 'MISSING_CHECKER'}
  if(-not $GStreamerBin){
    $options=@(
      (Join-Path $env:LOCALAPPDATA 'Programs\gstreamer\1.0\msvc_x86_64\bin'),
      (Join-Path $env:ProgramFiles 'gstreamer\1.0\msvc_x86_64\bin'),
      'C:\gstreamer\1.0\msvc_x86_64\bin')
    foreach($option in $options){
      if($option -and (Test-Path -LiteralPath (Join-Path $option 'gst-launch-1.0.exe') -PathType Leaf)){$GStreamerBin=$option;break}
    }
    if(-not $GStreamerBin){
      $g=Get-Command gst-launch-1.0.exe -ErrorAction SilentlyContinue
      if($g){$GStreamerBin=Split-Path -Parent $g.Source}
    }
  }
  if(-not $GStreamerBin){throw 'NO_SDK'}
  $line=@(& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $check -GStreamerBin $GStreamerBin -ReferenceManifest $ReferenceManifest 2>$null)
  if($LASTEXITCODE -ne 0 -or $line.Count -ne 1){throw 'FINGERPRINT_FAILED'}
  $l=[string]$line[0]
  if($l -notmatch '^C545D_HOST_GIO_FINGERPRINT,' -or
     $l -notmatch ',dll_found=6,dll_hash_matched=6,' -or
     $l -notmatch ',dll_missing=0,pe64_failed=0,' -or
     $l -notmatch ',recorder_active=0,' -or
     $l -notmatch ',pinned_sdk_match=1,' -or
     $l -notmatch ',install_approved=0,live_test_authorized=0,' -or
     ($l -notmatch ',windows10=1,' -and -not $isCi)){throw 'HOST_NOT_ELIGIBLE'}
  if(@(Get-Process -Name 'gst-launch-1.0','C545D_Recorder' -ErrorAction SilentlyContinue).Count -ne 0){throw 'RECORDER_ACTIVE'}
  if(-not (Test-Path -LiteralPath $CandidateDll -PathType Leaf) -or
     -not (Test-Path -LiteralPath $CandidateManifest -PathType Leaf) -or
     (Get-FileHash -LiteralPath $CandidateDll -Algorithm SHA256).Hash -ne $rc){throw 'CANDIDATE_BAD'}
  $manifest=[IO.File]::ReadAllText((Resolve-Path -LiteralPath $CandidateManifest).Path)
  if($manifest -notmatch ('(?m)^CANDIDATE_GIO_SHA256='+$rc+'\r?$') -or
     $manifest -notmatch ('(?m)^REFERENCE_GIO_SHA256='+$sdk+'\r?$') -or
     $manifest -notmatch '(?m)^C545D_RELEASE_CANDIDATE_STATUS=CI_TEST_ONLY_NOT_APPROVED_FOR_HOST\r?$'){
    throw 'MANIFEST_BAD'
  }
  $original=Join-Path $GStreamerBin 'gio-2.0-0.dll'
  $exe=Join-Path $GStreamerBin 'gst-launch-1.0.exe'
  $root=Split-Path -Parent $GStreamerBin
  $scanner=Join-Path $root 'libexec\gstreamer-1.0\gst-plugin-scanner.exe'
  $plugins=Join-Path $root 'lib\gstreamer-1.0'
  if(-not (Test-Path -LiteralPath $scanner -PathType Leaf) -or
     -not (Test-Path -LiteralPath $plugins -PathType Container)){throw 'SDK_INCOMPLETE'}
  $before1=(Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash
  $before2=(Get-FileHash -LiteralPath $CandidateDll -Algorithm SHA256).Hash
  $temp=if($isCi){$env:RUNNER_TEMP}else{$env:TEMP}
  $temp=[IO.Path]::GetFullPath($temp).TrimEnd('\')
  $t=Get-Item -LiteralPath $temp -Force
  if(-not $t.PSIsContainer -or ($t.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'BAD_TEMP'}
  $stage=Join-Path $temp ('c545d-private-gio-'+[guid]::NewGuid().ToString('N'))
  if(Test-Path -LiteralPath $stage){throw 'STAGE_EXISTS'}
  New-Item -ItemType Directory -Path $stage | Out-Null
  [IO.File]::WriteAllText((Join-Path $stage '.c545d-owned'),'C545D_ISOLATED_GIO_SMOKE')
  $owned=$true
  $bin=Join-Path $stage 'bin'
  New-Item -ItemType Directory -Path $bin | Out-Null
  $testExe=Join-Path $bin 'gst-launch-1.0.exe'
  $testGio=Join-Path $bin 'gio-2.0-0.dll'
  Copy-Item -LiteralPath $exe -Destination $testExe
  Copy-Item -LiteralPath $CandidateDll -Destination $testGio
  if((Get-FileHash -LiteralPath $testGio -Algorithm SHA256).Hash -ne $rc -or
     (Get-FileHash -LiteralPath $testExe -Algorithm SHA256).Hash -ne
     (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash){throw 'BAD_OVERLAY'}
  foreach($k in @('PATH','GST_REGISTRY','GST_PLUGIN_SCANNER','GST_PLUGIN_SYSTEM_PATH_1_0')){
    $prior[$k]=[Environment]::GetEnvironmentVariable($k,'Process')
  }
  $env:PATH="$bin;$GStreamerBin;$($prior['PATH'])"
  $env:GST_REGISTRY=Join-Path $stage 'isolated-registry.bin'
  $env:GST_PLUGIN_SCANNER=$scanner
  $env:GST_PLUGIN_SYSTEM_PATH_1_0=$plugins
  if(@(Get-Process -Name 'gst-launch-1.0','C545D_Recorder' -ErrorAction SilentlyContinue).Count -ne 0){
    throw 'RECORDER_BECAME_ACTIVE'
  }
  $out=Join-Path $stage 'isolated.wav'
  $uri=([Uri]::new([IO.Path]::GetFullPath($out))).AbsoluteUri
  $args=@('-e','-q','audiotestsrc','is-live=true','num-buffers=480',
    '!','audioconvert','!','audio/x-raw,format=S16LE,rate=48000,channels=1',
    '!','wavenc','!','giosink',('location='+$uri))
  $child=Start-Process -FilePath $testExe -ArgumentList $args -PassThru -WorkingDirectory $stage -RedirectStandardOutput (Join-Path $stage 'stdout') -RedirectStandardError (Join-Path $stage 'stderr')
  $started=1;$childExited=$false
  $handle=[C545DHostGioSmokeQuery]::OpenProcess([uint32]0x1000,$false,$child.Id)
  if($handle -eq [IntPtr]::Zero){throw 'NO_CHILD_QUERY_HANDLE'}
  for($i=0;$i -lt 300;$i++){
    Start-Sleep -Milliseconds 100
    try {
      $modules=@((Get-Process -Id $child.Id -ErrorAction Stop).Modules | Where-Object {$_.ModuleName -ieq 'gio-2.0-0.dll'})
      if($modules.Count -eq 1){
        $actual=[IO.Path]::GetFullPath($modules[0].FileName).TrimEnd('\')
        $wanted=[IO.Path]::GetFullPath($testGio).TrimEnd('\')
        if(-not [string]::Equals($actual,$wanted,[StringComparison]::OrdinalIgnoreCase)){throw 'WRONG_DLL'}
        $observed=1;break
      }
    }catch [System.InvalidOperationException] {} catch [System.ComponentModel.Win32Exception] {}
    if($child.HasExited){break}
  }
  if($observed -ne 1){throw 'MODULE_NOT_OBSERVED'}
  if(-not $child.WaitForExit(30000)){throw 'CHILD_TIMEOUT'}
  $childExited=$true
  [uint32]$code=259
  if(-not [C545DHostGioSmokeQuery]::GetExitCodeProcess($handle,[ref]$code) -or $code -ne 0){throw 'CHILD_FAILED'}
  $cleanExit=1
  if(-not (Test-Path -LiteralPath $out -PathType Leaf) -or (Get-Item -LiteralPath $out).Length -lt 30000){
    throw 'NO_WAV'
  }
  $wav=1
  $originals=[int]((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash -eq $before1 -and
                   (Get-FileHash -LiteralPath $CandidateDll -Algorithm SHA256).Hash -eq $before2)
  if($originals -ne 1){throw 'INPUT_CHANGED'}
  $reason=if($isCi){'CI_SYNTHETIC_PASS'}else{'WIN10_SYNTHETIC_PASS_NOT_LIVE_APPROVAL'}
} catch {
  # Only allow-listed fixed reason identifiers; never print native exception
  # text, local filenames, host paths, credentials, or raw process stderr.
  $code=[string]$_.Exception.Message
  $known=@('NOT_CI','MISSING_CHECKER','NO_SDK','FINGERPRINT_FAILED',
    'HOST_NOT_ELIGIBLE','RECORDER_ACTIVE','CANDIDATE_BAD','MANIFEST_BAD',
    'SDK_INCOMPLETE','BAD_TEMP','STAGE_EXISTS','BAD_OVERLAY',
    'RECORDER_BECAME_ACTIVE','NO_CHILD_QUERY_HANDLE','WRONG_DLL',
    'MODULE_NOT_OBSERVED','CHILD_TIMEOUT','CHILD_FAILED','NO_WAV',
    'INPUT_CHANGED')
  if($code -in $known){$reason=$code}else{$reason='BLOCKED'}
} finally {
  if($handle -ne [IntPtr]::Zero){[void][C545DHostGioSmokeQuery]::CloseHandle($handle)}
  if($child){
    if(-not $child.HasExited){
      # Only dispose of the private test child created by this invocation.
      try{$child.Kill();[void]$child.WaitForExit(5000)}catch{}
    }
    $childExited=[bool]$child.HasExited
    $child.Dispose()
  }
  foreach($k in $prior.Keys){[Environment]::SetEnvironmentVariable($k,$prior[$k],'Process')}
  if($owned -and $stage -and $childExited){
    try {
      $item=Get-Item -LiteralPath $stage -Force -ErrorAction Stop
      $parent=[IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($stage)).TrimEnd('\')
      if($item.PSIsContainer -and
         ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 -and
         [string]::Equals($parent,$temp,[StringComparison]::OrdinalIgnoreCase) -and
         [IO.Path]::GetFileName($stage) -match '^c545d-private-gio-[a-f0-9]{32}$' -and
         [IO.File]::ReadAllText((Join-Path $stage '.c545d-owned')) -ceq 'C545D_ISOLATED_GIO_SMOKE'){
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction Stop
        $cleanup=[int](-not (Test-Path -LiteralPath $stage))
      }
    } catch {$cleanup=0}
  }
}
$passed=[int]($started -eq 1 -and $observed -eq 1 -and $wav -eq 1 -and
              $cleanExit -eq 1 -and $originals -eq 1 -and $cleanup -eq 1)
if($passed -ne 1){$reason='BLOCKED'}
Write-Output "C545D_GIO_ISOLATED_SMOKE,started=$started,loaded_expected=$observed,wav_ok=$wav,exit_ok=$cleanExit,rollback_ok=$cleanup,originals_unchanged=$originals,install_approved=0,live_tapo_authorized=0,reason=$reason"
if($passed -eq 1){exit 0}
exit 3
