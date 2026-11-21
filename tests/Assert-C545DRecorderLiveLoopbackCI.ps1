#Requires -Version 5.1
<#
 CI-only integration smoke for byte-equivalent Record.ps1 and two finite
 localhost RTSP inputs. Does NOT touch a user's PC, camera, settings,
 installed GStreamer, active recording, or credentials.
 Source retains exact 3600s splitmux and original codec/clock/stop policy.
 This intentionally tests natural finite-RTSP source termination, NOT GUI
 Ctrl+C stop. Full EOS/reconnect/Win10 remains a separate gate.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SdkRoot,
  [Parameter(Mandatory=$true)][string]$CandidateDll,
  [Parameter(Mandatory=$true)][string]$ReferenceManifest
)
$ErrorActionPreference='Stop'
$pin=@{
  'gio-2.0-0.dll'='A875107C180FB248236D1E96E14F362F117124DF2FEE1237FA2142B7B363941B'
  'glib-2.0-0.dll'='CAF29CFC1467E3A3E5E91F0F649BD7A501107D9B3C32A2866B08E2ECFA209E3E'
  'gobject-2.0-0.dll'='811DAB4B420E520D91AC3FE5202975CC90CAF2C53EF2F8F0FCE8F8588A735C7A'
  'gmodule-2.0-0.dll'='86BE81A7011EC07E1992CE7A742AD881A80AE38583BBCFFBF973498D4748DAC5'
  'intl-8.dll'='2EF6A23F712FD7B9BF72B2FEF1A1FD5CDE27BA88F7D164E9E6DE18936C1F51B0'
  'z-1.dll'='B84851F9084247F466C076EE993BD5A92F3462466C4877B5C4ECC4125743A060'
}
$candidateSha='67B9F7246E4744FEF7EE1EAD3BED4CE2179C6F0465EC68A92D01DD12B4A3CCAD'
$stage=$null;$server=$null;$stopJob=$null;$owned=$false
$phase='PREP';$serverReady=$false;$recordExit=259;$filesCount=0
$launchObserved=0;$policyStop=0;$eosObserved=0;$mp4Decoded=0
$metric=@{};$snapshot=@{};$prior=@{}
try {
  if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
     -not $env:RUNNER_TEMP){throw 'NOT_DISPOSABLE_WINDOWS_CI'}
  $temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
  $tempObj=Get-Item -LiteralPath $temp -Force
  if(-not $tempObj.PSIsContainer -or
     ($tempObj.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'UNSAFE_CI_TEMP'}
  $sdkBin=Join-Path $SdkRoot 'bin'
  $sdkRef=Get-Content -LiteralPath $ReferenceManifest -Raw | ConvertFrom-Json
  if($sdkRef.schema -ne 1 -or $sdkRef.install_approved -ne $false -or
     $sdkRef.sdk -cne 'gstreamer-1.0-msvc-x86_64-1.28.8' -or
     @($sdkRef.dll_sha256.PSObject.Properties.Name).Count -ne 6 -or
     ([string]$sdkRef.candidate_sha256).ToUpperInvariant() -cne $candidateSha){
    throw 'REFERENCE_NOT_PINNED'
  }
  foreach($key in $pin.Keys){
    if(([string]$sdkRef.dll_sha256.PSObject.Properties[$key].Value).ToUpperInvariant() -cne $pin[$key] -or
       (Get-FileHash -LiteralPath (Join-Path $sdkBin $key) -Algorithm SHA256).Hash -cne $pin[$key]){
      throw 'OFFICIAL_SDK_CHANGED'
    }
  }
  if((Get-FileHash -LiteralPath $CandidateDll -Algorithm SHA256).Hash -cne $candidateSha){
    throw 'CANDIDATE_CHANGED'
  }
  $source=(Resolve-Path -LiteralPath 'Record.ps1').Path
  $settings=(Resolve-Path -LiteralPath 'CommonSettings.ps1').Path
  foreach($src in @($source,$settings,$CandidateDll)){
    $snapshot[$src]=(Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
  }
  $stage=Join-Path $temp ('c545d-ci-production-mirror-'+[guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
  [IO.File]::WriteAllText((Join-Path $stage '.c545d-ci-owned'),'CI_MIRROR_ONLY_NOT_FOR_EXECUTION')
  $owned=$true
  $bin=Join-Path $stage 'bin'
  New-Item -ItemType Directory -Path $bin | Out-Null
  foreach($exe in @('gst-launch-1.0.exe','gst-inspect-1.0.exe','gst-discoverer-1.0.exe')){
    Copy-Item -LiteralPath (Join-Path $sdkBin $exe) -Destination (Join-Path $bin $exe)
    if((Get-FileHash -LiteralPath (Join-Path $bin $exe) -Algorithm SHA256).Hash -cne
       (Get-FileHash -LiteralPath (Join-Path $sdkBin $exe) -Algorithm SHA256).Hash){
      throw 'STAGED_EXE_CHANGED'
    }
  }
  Copy-Item -LiteralPath $CandidateDll -Destination (Join-Path $bin 'gio-2.0-0.dll')
  if((Get-FileHash -LiteralPath (Join-Path $bin 'gio-2.0-0.dll') -Algorithm SHA256).Hash -cne $candidateSha){
    throw 'STAGED_GIO_CHANGED'
  }
  $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $rows=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File 'tools/New-C545DIsolatedProductionMirrorCI.ps1' -RecordSource $source -SettingsSource $settings -StageRoot $stage)
  if($LASTEXITCODE -ne 0 -or $rows.Count -ne 1 -or
     $rows[0] -cne 'C545D_PRODUCTION_MIRROR,rendered=1,exact_one_statement=1,source_syntax=1,candidate_pinned=1,host_executed=0,rtsp_contacted=0,install_approved=0,live_tapo_authorized=0,reason=CI_ONLY_MIRROR_PASS'){
    throw 'SOURCE_MIRROR_REFUSED'
  }
  $rows=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File 'tools/New-C545DPrivateOutputSettingsMirrorCI.ps1' -StageRoot $stage -OriginalSettingsSource $settings)
  if($LASTEXITCODE -ne 0 -or $rows.Count -ne 1 -or
     $rows[0] -cne 'C545D_PRIVATE_OUTPUT_MIRROR,patched=1,single_assignment=1,source_syntax=1,private_only=1,host_executed=0,rtsp_contacted=0,install_approved=0,live_tapo_authorized=0,reason=CI_PRIVATE_OUTPUT_MIRROR_PASS'){
    throw 'OUTPUT_MIRROR_REFUSED'
  }
  $expected=[IO.File]::ReadAllText($source).Replace('$bin = Find-GstBin',
      ('$bin = [IO.Path]::GetFullPath('''+$bin.Replace("'","''")+''')'))
  if([IO.File]::ReadAllText((Join-Path $stage 'Record.ps1')) -cne $expected){
    throw 'RECORDER_MIRROR_NOT_EXACT'
  }
  $phase='ENV'
  foreach($key in @('PATH','LOCALAPPDATA','GST_PLUGIN_SCANNER','GST_REGISTRY',
      'GST_PLUGIN_PATH','GST_PLUGIN_PATH_1_0',
      'GST_PLUGIN_SYSTEM_PATH','GST_PLUGIN_SYSTEM_PATH_1_0')){
    $prior[$key]=[Environment]::GetEnvironmentVariable($key,'Process')
  }
  $env:PATH="$bin;$sdkBin;$($prior['PATH'])"
  $env:GST_PLUGIN_SCANNER=Join-Path $SdkRoot 'libexec\gstreamer-1.0\gst-plugin-scanner.exe'
  $env:GST_REGISTRY=Join-Path $stage 'registry.bin'
  $env:GST_PLUGIN_PATH=''
  $env:GST_PLUGIN_PATH_1_0=''
  $env:GST_PLUGIN_SYSTEM_PATH=''
  $env:GST_PLUGIN_SYSTEM_PATH_1_0=Join-Path $SdkRoot 'lib\gstreamer-1.0'
  $localData=Join-Path $stage 'ci-localappdata'
  $config=Join-Path $localData 'C545D_GStreamer'
  New-Item -ItemType Directory -Path $config -Force | Out-Null
  @{
    camera_ip='127.0.0.1'
    camera_user='CI_SYNTHETIC_NO_AUTH'
    output_folder='C:\INVALID_NOT_USED'
  } | ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $config 'settings.json') -Encoding UTF8
  $dummyScript=Join-Path $stage 'create-fake-secret.ps1'
  [IO.File]::WriteAllText($dummyScript,(
    'param([string]$Path)'+[Environment]::NewLine+
    '$fake=ConvertTo-SecureString ''CI_DUMMY_NOT_REAL'' -AsPlainText -Force'+[Environment]::NewLine+
    'ConvertFrom-SecureString $fake | Set-Content -LiteralPath $Path -Encoding ASCII'
  ))
  $dummyFile=Join-Path $config 'camera_password.dpapi'
  & $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $dummyScript -Path $dummyFile
  if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $dummyFile)){
    throw 'DUMMY_SECRET_SETUP_FAILED'
  }
  $env:LOCALAPPDATA=$localData
  $stop=Join-Path $stage 'ci-live.stop'
  if(Test-Path -LiteralPath $stop){throw 'EARLY_STOP_MARKER'}
  $phase='COMPILER'
  $lib=Join-Path $SdkRoot 'lib'
  $inc=Join-Path $SdkRoot 'include'
  $exe=Join-Path $stage 'c545d_finite_rtsp_server.exe'
  $args=@('/nologo','/W4','/MD','/O2','/TC',
    ('/I'+(Join-Path $inc 'gstreamer-1.0')),
    ('/I'+(Join-Path $inc 'glib-2.0')),
    ('/I'+(Join-Path $lib 'glib-2.0\include')),
    'tests/c545d_ci_finite_rtsp_server.c',('/Fe:'+$exe),
    '/link',('/LIBPATH:'+$lib),
    'gstrtspserver-1.0.lib','gstreamer-1.0.lib','gobject-2.0.lib','glib-2.0.lib')
  $compileOutput=@(& cl.exe @args 2>&1)
  if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $exe)){
    throw 'FINITE_RTSP_COMPILE_FAILED'
  }
  $phase='RTSP_BIND'
  $svrOut=Join-Path $stage 'server.stdout'
  $svrErr=Join-Path $stage 'server.stderr'
  $server=Start-Process -FilePath $exe -ArgumentList 'server' -PassThru -WorkingDirectory $temp -RedirectStandardOutput $svrOut -RedirectStandardError $svrErr
  $ready='C545D_FINITE_RTSP_SERVER,ready=1,loopback_only=1,port=554,streams=2,video_frames_per_stream=330,pcma_buffers_per_stream=550,real_camera=0'
  for($i=0;$i -lt 160;$i++){
    Start-Sleep -Milliseconds 100
    if($server.HasExited){break}
    if(Test-Path -LiteralPath $svrOut){
      try {
        $fd=[IO.File]::Open($svrOut,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
        try {
          $rdr=[IO.StreamReader]::new($fd)
          $serverReady=$rdr.ReadToEnd().Contains($ready)
        } finally {$fd.Dispose()}
      } catch [IO.IOException] {}
    }
    if($serverReady){break}
  }
  if(-not $serverReady){throw 'FINITE_RTSP_NOT_READY'}
  $phase='RECORDER_LIVE'
  # The watchdog ONLY writes the existing GUI-style stop marker. It does
  # not send CTRL+C, kill a recording, or pretend to have tested GUI EOS.
  # If the finite RTSP source does not complete, the workflow timeout
  # eventually fails this disposable CI probe, not the user's recorder.
  $stopJob=Start-Job -ArgumentList $stage,$stop,$svrOut -ScriptBlock {
    param([string]$ownedStage,[string]$stopPath,[string]$serverStdout)
    if([IO.File]::ReadAllText((Join-Path $ownedStage '.c545d-ci-owned')) -cne
       'CI_MIRROR_ONLY_NOT_FOR_EXECUTION'){return 'ownership=0'}
    $watch=[Diagnostics.Stopwatch]::StartNew()
    $bothMountedAt=-1
    while($watch.Elapsed.TotalSeconds -lt 95){
      $media=''
      if(Test-Path -LiteralPath $serverStdout){
        try {
          $fd=[IO.File]::Open($serverStdout,[IO.FileMode]::Open,
                 [IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
          try {
            $reader=[IO.StreamReader]::new($fd)
            $media=$reader.ReadToEnd()
          } finally {$fd.Dispose()}
        } catch [IO.IOException] {}
      }
      $wide=$media.Contains('C545D_FINITE_RTSP_MEDIA_CONFIGURED,stream=stream1,real_camera=0')
      $tele=$media.Contains('C545D_FINITE_RTSP_MEDIA_CONFIGURED,stream=stream6,real_camera=0')
      if($wide -and $tele -and $bothMountedAt -lt 0){
        $bothMountedAt=$watch.Elapsed.TotalSeconds
      }
      # Six seconds AFTER both actual RTSP sessions are constructed, record
      # the existing stop marker. This happens before the finite 22s source
      # stops, and is independent of MP4 buffering/delayed file writes.
      if($bothMountedAt -ge 0 -and
         ($watch.Elapsed.TotalSeconds-$bothMountedAt) -gt 6){
        [IO.File]::WriteAllText($stopPath,'CI_TWO_LOCAL_RTSP_MOUNTS_ACTIVE')
        return 'marker=1,two_mounts=1,real_camera=0'
      }
      if($watch.Elapsed.TotalSeconds -gt 55 -and $bothMountedAt -lt 0){
        [IO.File]::WriteAllText($stopPath,'CI_MOUNTS_NOT_READY_STOP_RECONNECT')
        return 'marker=1,two_mounts=0,real_camera=0'
      }
      Start-Sleep -Milliseconds 250
    }
    [IO.File]::WriteAllText($stopPath,'CI_MOUNT_WAIT_TIMEOUT')
    return 'marker=1,timed_out=1'
  }
  $recorder=Join-Path $stage 'Record.ps1'
  $privateErr=Join-Path $stage 'record.stderr'
  $stdout=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $recorder -StopFile $stop 2> $privateErr)
  $recordExit=$LASTEXITCODE
  $text=$stdout -join [Environment]::NewLine
  [IO.File]::WriteAllText((Join-Path $stage 'record.stdout'),$text)
  $launchObserved=[int]$text.Contains('GStreamer launching (EOS enabled); attempt=1')
  $policyStop=[int]$text.Contains('Recorder exit policy: stop')
  $eosObserved=[int]$text.Contains('Recording stopped by GUI; GStreamer EOS completed.')
  $actualRtspError=[int]([IO.File]::ReadAllText($privateErr) -match 'Could not connect to server|404 Not Found|Unauthorized')
  $outFiles=@(Get-ChildItem -LiteralPath (Join-Path $stage 'private-output') -Filter '*.mp4' -File -ErrorAction SilentlyContinue)
  $filesCount=$outFiles.Count
  $safeStop=Test-Path -LiteralPath $stop
  $returnObserved=[int]$text.Contains('GStreamer returned; exitCode=')
  $launches=[regex]::Matches($text,'GStreamer launching \(EOS enabled\); attempt=').Count
  $lastExit=[regex]::Matches($text,'GStreamer returned; exitCode=(-?[0-9]+); stopMarker=(True|False)')
  $nativeRc=if($lastExit.Count -gt 0){[int]$lastExit[$lastExit.Count-1].Groups[1].Value}else{999}
  $markerAtReturn=[int]($lastExit.Count -gt 0 -and $lastExit[$lastExit.Count-1].Groups[2].Value -ceq 'True')
  $reconnectAction=[int]$text.Contains('Recorder exit policy: reconnect')
  $lastMp4Bytes=if($filesCount -gt 0){[long]$outFiles[0].Length}else{0}
  $srvStream=''
  if(Test-Path -LiteralPath $svrOut){
    $readFd=[IO.File]::Open($svrOut,[IO.FileMode]::Open,
                 [IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
    try {
      $streamReader=[IO.StreamReader]::new($readFd)
      $srvStream=$streamReader.ReadToEnd()
    } finally {$readFd.Dispose()}
  }
  $wideRequested=[int]$srvStream.Contains('C545D_FINITE_RTSP_MEDIA_CONFIGURED,stream=stream1,real_camera=0')
  $teleRequested=[int]$srvStream.Contains('C545D_FINITE_RTSP_MEDIA_CONFIGURED,stream=stream6,real_camera=0')
  Write-Output "C545D_RECORDER_LIVE_RTSP_STAGE,launch=$launchObserved,launch_count=$launches,returned=$returnObserved,source_stop_marker=$([int]$safeStop),stop_at_gst_return=$markerAtReturn,wide_rtsp_requested=$wideRequested,tele_rtsp_requested=$teleRequested,policy_stop=$policyStop,policy_reconnect=$reconnectAction,gst_exit=$nativeRc,eos_message=$eosObserved,mp4_count=$filesCount,first_mp4_bytes=$lastMp4Bytes,rtsp_error=$actualRtspError,record_exit_nonzero=$([int]($recordExit -ne 0)),real_camera=0"
  if($recordExit -ne 0 -or $launchObserved -ne 1 -or
     $launches -ne 1 -or -not $safeStop -or $markerAtReturn -ne 1 -or
     $wideRequested -ne 1 -or $teleRequested -ne 1 -or $policyStop -ne 1 -or
     $filesCount -ne 1 -or $actualRtspError -ne 0){
    throw 'RECORDER_LIVE_GATE_NOT_PASSED'
  }
  $phase='MP4_VERIFY'
  $f=$outFiles[0]
  if($f.Length -lt 30000){throw 'MP4_TOO_SMALL'}
  $uri=([Uri]$f.FullName).AbsoluteUri
  $info=(& (Join-Path $bin 'gst-discoverer-1.0.exe') -v $uri 2>&1 | Out-String)
  if($LASTEXITCODE -ne 0){throw 'LIVE_MP4_DISCOVER_FAILED'}
  foreach($term in @('(?i)h\.?264|video/x-h264','(?i)aac|audio/mpeg',
      '(?i)width:\s*2560','(?i)height:\s*720',
      '(?i)(frame rate|framerate):\s*15/1',
      '(?i)(sample rate|rate):\s*48000',
      '(?i)channels:\s*1\b')){
    if($info -notmatch $term){throw 'LIVE_MP4_CAPS_INVALID'}
  }
  $dec=@('-q','filesrc',("location="+$f.FullName.Replace('\','/')),
      '!','qtdemux','name=d',
      'd.video_0','!','queue','!','h264parse','!','avdec_h264',
      '!','fakesink','sync=false',
      'd.audio_0','!','queue','!','aacparse','!','avdec_aac',
      '!','fakesink','sync=false')
  $decodeOutput=@(& (Join-Path $bin 'gst-launch-1.0.exe') @dec 2>&1)
  if($LASTEXITCODE -ne 0){throw 'LIVE_MP4_DECODE_FAILED'}
  $mp4Decoded=1
  foreach($src in $snapshot.Keys){
    if((Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash -cne $snapshot[$src]){
      throw 'ORIGINAL_BYTES_CHANGED'
    }
  }
  $phase='PASS'
} catch {
  $known=@('NOT_DISPOSABLE_WINDOWS_CI','UNSAFE_CI_TEMP','REFERENCE_NOT_PINNED',
    'OFFICIAL_SDK_CHANGED','CANDIDATE_CHANGED','SOURCE_MIRROR_REFUSED',
    'OUTPUT_MIRROR_REFUSED','RECORDER_MIRROR_NOT_EXACT','STAGED_EXE_CHANGED',
    'STAGED_GIO_CHANGED','DUMMY_SECRET_SETUP_FAILED','FINITE_RTSP_COMPILE_FAILED',
    'FINITE_RTSP_NOT_READY','RECORDER_LIVE_GATE_NOT_PASSED','MP4_TOO_SMALL',
    'LIVE_MP4_DISCOVER_FAILED','LIVE_MP4_CAPS_INVALID','LIVE_MP4_DECODE_FAILED',
    'ORIGINAL_BYTES_CHANGED','EARLY_STOP_MARKER')
  $reason=if($_.Exception.Message -in $known){$_.Exception.Message}else{'BLOCKED'}
  Write-Output "C545D_RECORDER_LIVE_RTSP_FAIL,phase=$phase,reason=$reason,real_camera=0,host_modified=0"
  throw 'SANITIZED_CI_LOOPBACK_RECORD_TEST_FAILED'
} finally {
  if($stopJob){
    try {
      if($stopJob.State -eq 'Running'){Stop-Job -Job $stopJob -ErrorAction SilentlyContinue}
      [void](Receive-Job -Job $stopJob -ErrorAction SilentlyContinue)
      Remove-Job -Job $stopJob -Force -ErrorAction SilentlyContinue
    } catch {}
  }
  if($server){
    if(-not $server.HasExited){try{$server.Kill();[void]$server.WaitForExit(5000)}catch{}}
    $server.Dispose()
  }
  foreach($key in $prior.Keys){
    [Environment]::SetEnvironmentVariable($key,$prior[$key],'Process')
  }
  if($owned -and $stage -and (Test-Path -LiteralPath $stage)){
    $dir=Get-Item -LiteralPath $stage -Force
    $links=@(Get-ChildItem -LiteralPath $stage -Recurse -Force -ErrorAction Stop |
      Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0})
    if(-not $dir.PSIsContainer -or
       ($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
       $links.Count -ne 0 -or
       -not [string]::Equals([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($stage)).TrimEnd('\'),
                            $temp,[StringComparison]::OrdinalIgnoreCase) -or
       [IO.Path]::GetFileName($stage) -notmatch '^c545d-ci-production-mirror-[a-f0-9]{32}$' -or
       [IO.File]::ReadAllText((Join-Path $stage '.c545d-ci-owned')) -cne
       'CI_MIRROR_ONLY_NOT_FOR_EXECUTION'){
      throw 'OWNED_STAGE_CLEANUP_REFUSED'
    }
    Remove-Item -LiteralPath $stage -Force -Recurse -ErrorAction Stop
    if(Test-Path -LiteralPath $stage){throw 'STAGE_CLEANUP_INCOMPLETE'}
  }
}
if($phase -cne 'PASS' -or $mp4Decoded -ne 1 -or $eosObserved -ne 1){
  throw 'INFLIGHT_RTSP_EOS_NOT_QUALIFIED'
}
Write-Output 'C545D_RECORDER_REAL_SOURCE_LOCAL_RTSP_CI_PASS,real_recorder=1,rtsp_two_mounts=1,mp4_h264_aac=1,mp4_decodable=1,inflight_stop_marker=1,source_eos=1,gui_ctrl_c_tested=0,real_tapo_tested=0,real_hourly_split_tested=0,install_approved=0,owned_rollback=1'
