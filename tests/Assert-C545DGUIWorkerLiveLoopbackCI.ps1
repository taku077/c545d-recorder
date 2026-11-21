#Requires -Version 5.1
<#
 CI-only integrated GUI worker control test. Exact RecordGUIWorker.ps1 and
 byte-equivalent Record.ps1 run in their own private Windows console while
 two synthetic RTSP streams play. Send durable STOP marker THEN CTRL_C_EVENT
 only when the console contains exclusively our worker, gst-launch, sender.
 No camera, user PC, host DLL changes, credentials or registry modifications.
 Optional CI-only eight-second split exercises multiple finalized MP4 fragments,
 NOT the actual 3600s boundary. Source equivalence applies only in default mode.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SdkRoot,
  [Parameter(Mandatory=$true)][string]$CandidateDll,
  [Parameter(Mandatory=$true)][string]$ReferenceManifest,
  [ValidateSet(0,8)][int]$CiSplitSeconds=0
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
$stage=$null;$server=$null;$worker=$null;$owned=$false;$signalSent=0;$workerExited=0
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
  $workerSource=(Resolve-Path -LiteralPath 'RecordGUIWorker.ps1').Path
  $guiSource=(Resolve-Path -LiteralPath 'C545D_App.ps1').Path
  foreach($src in @($source,$settings,$CandidateDll,$workerSource,$guiSource)){
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
  # Explicit opt-in, CI-ONLY accelerated segment test. The original mirror
  # has already passed exact one-statement equivalence. Modify ONLY a private
  # disposable clone and require a byte-for-byte reversible single token.
  if($CiSplitSeconds -eq 8){
    $recorderMirror=Join-Path $stage 'Record.ps1'
    $originalMirror=[IO.File]::ReadAllText($recorderMirror)
    $beforeToken="'max-size-time=3600000000000'"
    $afterToken="'max-size-time=8000000000'"
    if([regex]::Matches($originalMirror,[regex]::Escape($beforeToken)).Count -ne 1){
      throw 'CI_SPLIT_ANCHOR_NOT_UNIQUE'
    }
    $shortMirror=$originalMirror.Replace($beforeToken,$afterToken)
    if($shortMirror.Replace($afterToken,$beforeToken) -cne $expected){
      throw 'CI_SPLIT_MIRROR_NOT_REVERSIBLE'
    }
    $tok=$null;$parseErr=$null
    [void][Management.Automation.Language.Parser]::ParseInput($shortMirror,[ref]$tok,[ref]$parseErr)
    if($parseErr.Count -ne 0){throw 'CI_SPLIT_SOURCE_SYNTAX'}
    [IO.File]::WriteAllText($recorderMirror,$shortMirror,(New-Object System.Text.UTF8Encoding($false)))
  }
  # The actual GUI worker source is copied byte-for-byte, not patched.
  Copy-Item -LiteralPath $workerSource -Destination (Join-Path $stage 'RecordGUIWorker.ps1')
  if((Get-FileHash -LiteralPath (Join-Path $stage 'RecordGUIWorker.ps1') -Algorithm SHA256).Hash -cne
      $snapshot[$workerSource]){throw 'GUI_WORKER_MIRROR_NOT_EXACT'}

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
  # Dummy DPAPI is created INSIDE the actual spawned worker process, so
  # Windows hosted runner's Start-Process token differences cannot break
  # decrypt. Only synthetic values and a CI-private LOCALAPPDATA are used.
  $session=[guid]::NewGuid().ToString('N')
  $control=Join-Path $config 'Control'
  New-Item -ItemType Directory -Path $control -Force | Out-Null
  $stop=Join-Path $control ('session_'+$session+'.stop')
  $ready=Join-Path $control ('session_'+$session+'.ready')
  if((Test-Path -LiteralPath $stop) -or (Test-Path -LiteralPath $ready)){
    throw 'EARLY_WORKER_MARKER'
  }
  $bootstrap=Join-Path $stage 'ci-private-worker-bootstrap.ps1'
  $bootstrapText=@(
    'param([string]$OwnedStage,[string]$SessionId)',
    '$ErrorActionPreference=''Stop''',
    '$phase=Join-Path $OwnedStage ''ci-bootstrap-phase''',
    '[IO.File]::WriteAllText($phase,''BOOTSTRAP_ENTER'')',
    'if($env:GITHUB_ACTIONS -cne ''true'' -or $env:RUNNER_OS -cne ''Windows''){exit 3}',
    'if([IO.File]::ReadAllText((Join-Path $OwnedStage ''.c545d-ci-owned'')) -cne ''CI_MIRROR_ONLY_NOT_FOR_EXECUTION''){exit 3}',
    '[IO.File]::WriteAllText($phase,''GUARDS_PASS'')',
    '$env:LOCALAPPDATA=Join-Path $OwnedStage ''ci-localappdata''',
    '[IO.File]::WriteAllText($phase,''LOCALAPPDATA_SET'')',
    '$conf=Join-Path $env:LOCALAPPDATA ''C545D_GStreamer''',
    '[IO.File]::WriteAllText($phase,''CONFIG_PATH_BUILT'')',
    '$secret=Join-Path $conf ''camera_password.dpapi''',
    '[IO.File]::WriteAllText($phase,''SECRET_PATH_BUILT'')',
    'if(Test-Path -LiteralPath $secret){exit 3}',
    '[IO.File]::WriteAllText($phase,''BEFORE_DPAPI'')',
    'try {',
    ' $fake=ConvertTo-SecureString ''CI_DUMMY_NOT_REAL'' -AsPlainText -Force',
    '} catch {',
    ' $class=$_.Exception.GetType().Name',
    ' $allowed=@(''CommandNotFoundException'',''CryptographicException'',''ArgumentException'',''PSArgumentException'',''MethodInvocationException'',''RuntimeException'',''SecurityException'')',
    ' if($class -notin $allowed){$class=''Other''}',
    ' [IO.File]::WriteAllText($phase,''SECURESTRING_ERROR_''+$class)',
    ' exit 3',
    '}',
    '[IO.File]::WriteAllText($phase,''SECURESTRING_CREATED'')',
    '$cipher=ConvertFrom-SecureString $fake',
    '[IO.File]::WriteAllText($phase,''DPAPI_ENCRYPTED'')',
    '$cipher | Set-Content -LiteralPath $secret -Encoding ASCII',
    'if(-not (Test-Path -LiteralPath $secret -PathType Leaf)){exit 3}',
    '[IO.File]::WriteAllText($phase,''DUMMY_DPAPI_WRITTEN'')',
    '[IO.File]::WriteAllText($phase,''WORKER_INVOKED'')',
    'try {',
    ' & (Join-Path $OwnedStage ''RecordGUIWorker.ps1'') -SessionId $SessionId',
    ' if(-not $?){[IO.File]::WriteAllText($phase,''WORKER_RETURNED_FAILURE'');exit 3}',
    ' [IO.File]::WriteAllText($phase,''WORKER_RETURNED_SUCCESS'')',
    '} catch {',
    ' [IO.File]::WriteAllText($phase,''WORKER_THREW'')',
    ' exit 3',
    '}',
    'exit 0'
  )
  [IO.File]::WriteAllText($bootstrap,($bootstrapText -join [Environment]::NewLine),
      [Text.UTF8Encoding]::new($false))
  $env:LOCALAPPDATA=$localData
  $phase='COMPILER'
  $lib=Join-Path $SdkRoot 'lib'
  $inc=Join-Path $SdkRoot 'include'
  $exe=Join-Path $stage 'c545d_finite_rtsp_server.exe'
  $args=@('/nologo','/W4','/MD','/O2','/TC',
    ('/I'+(Join-Path $inc 'gstreamer-1.0')),
    ('/I'+(Join-Path $inc 'glib-2.0')),
    ('/I'+(Join-Path $lib 'glib-2.0\include')),
    '/DC545D_CI_RTSP_STEADY=1',
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
  $rtspReadyLine='C545D_FINITE_RTSP_SERVER,ready=1,loopback_only=1,port=554,streams=2,video_frames_per_stream=900,pcma_buffers_per_stream=1500,real_camera=0'
  for($i=0;$i -lt 160;$i++){
    Start-Sleep -Milliseconds 100
    if($server.HasExited){break}
    if(Test-Path -LiteralPath $svrOut){
      try {
        $fd=[IO.File]::Open($svrOut,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
        try {
          $rdr=[IO.StreamReader]::new($fd)
          $serverReady=$rdr.ReadToEnd().Contains($rtspReadyLine)
        } finally {$fd.Dispose()}
      } catch [IO.IOException] {}
    }
    if($serverReady){break}
  }
  if(-not $serverReady){throw 'FINITE_RTSP_NOT_READY'}
  $phase='GUI_WORKER_START'
  $workerArgs=@('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass',
      '-File',('"'+$bootstrap+'"'),'-OwnedStage',('"'+$stage+'"'),
      '-SessionId',$session)
  # A private WindowStyle Hidden console is identical to GUI launch policy.
  # Do not redirect the console, because gst-launch must receive Ctrl+C.
  # Microsoft about_PSModulePath: an intermediate Start-Process can pass
  # PowerShell7 modules into Windows PowerShell5.1, breaking standard
  # Microsoft.PowerShell.Security auto-loading (CommandNotFoundException).
  # Clear ONLY process env at CI child launch, then restore immediately.
  $previousModulePath=[Environment]::GetEnvironmentVariable('PSModulePath','Process')
  try {
    [Environment]::SetEnvironmentVariable('PSModulePath',$null,'Process')
    $worker=Start-Process -FilePath $ps -ArgumentList $workerArgs -WorkingDirectory $temp -WindowStyle Hidden -PassThru
  } finally {
    [Environment]::SetEnvironmentVariable('PSModulePath',$previousModulePath,'Process')
  }
  $readySeen=$false
  for($i=0;$i -lt 300;$i++){
    Start-Sleep -Milliseconds 100
    if($worker.HasExited){break}
    if(Test-Path -LiteralPath $ready){
      try { $readySeen=([IO.File]::ReadAllText($ready).Trim() -ceq [string]$worker.Id) }
      catch [IO.IOException] {}
      if($readySeen){break}
    }
  }
  if(-not $readySeen){
    $bootFile=Join-Path $stage 'ci-bootstrap-phase'
    $phaseValue=if(Test-Path -LiteralPath $bootFile){[IO.File]::ReadAllText($bootFile)}else{'NO_BOOTSTRAP_PHASE'}
    $allowed=@('NO_BOOTSTRAP_PHASE','BOOTSTRAP_ENTER','GUARDS_PASS',
       'LOCALAPPDATA_SET','CONFIG_PATH_BUILT','SECRET_PATH_BUILT',
       'BEFORE_DPAPI','SECURESTRING_CREATED','DPAPI_ENCRYPTED',
       'SECURESTRING_ERROR_CommandNotFoundException',
       'SECURESTRING_ERROR_CryptographicException',
       'SECURESTRING_ERROR_ArgumentException',
       'SECURESTRING_ERROR_PSArgumentException',
       'SECURESTRING_ERROR_MethodInvocationException',
       'SECURESTRING_ERROR_RuntimeException',
       'SECURESTRING_ERROR_SecurityException',
       'SECURESTRING_ERROR_Other',
       'DUMMY_DPAPI_WRITTEN','WORKER_INVOKED','WORKER_RETURNED_FAILURE',
       'WORKER_RETURNED_SUCCESS','WORKER_THREW')
    if($phaseValue -notin $allowed){$phaseValue='UNEXPECTED_PHASE'}
    $existsSecret=[int](Test-Path -LiteralPath (Join-Path $config 'camera_password.dpapi'))
    $existsReady=[int](Test-Path -LiteralPath $ready)
    $controlExists=[int](Test-Path -LiteralPath $control -PathType Container)
    $transcriptFolder=Join-Path $config 'Logs'
    $logCount=if(Test-Path -LiteralPath $transcriptFolder){
      @(Get-ChildItem -LiteralPath $transcriptFolder -Filter 'Recording_*.txt' -File -ErrorAction SilentlyContinue).Count
    }else{0}
    $privateFiles=if(Test-Path -LiteralPath (Join-Path $stage 'private-output')){
      @(Get-ChildItem -LiteralPath (Join-Path $stage 'private-output') -Filter '*.mp4' -File -ErrorAction SilentlyContinue).Count
    }else{0}
    $workerCpuMs=0
    if(-not $worker.HasExited){try{$workerCpuMs=[int]$worker.TotalProcessorTime.TotalMilliseconds}catch{}}
    $readyCandidates=@(Get-ChildItem -LiteralPath $control -Filter 'session_*.ready' -File -ErrorAction SilentlyContinue)
    $readyCandidatesCount=$readyCandidates.Count
    $readyCandidatePidMatch=0
    $readyCandidateNameMatch=0
    foreach($candidate in $readyCandidates){
      if($candidate.Name -ceq [IO.Path]::GetFileName($ready)){$readyCandidateNameMatch=1}
      if([IO.File]::ReadAllText($candidate.FullName).Trim() -ceq [string]$worker.Id){
        $readyCandidatePidMatch=1
      }
    }
    $logText=''
    if($logCount -eq 1){
      $transcript=(Get-ChildItem -LiteralPath $transcriptFolder -Filter 'Recording_*.txt' -File | Select-Object -First 1).FullName
      try {
        $fd=[IO.File]::Open($transcript,[IO.FileMode]::Open,
                 [IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
        try {
          $rdr=[IO.StreamReader]::new($fd)
          $logText=$rdr.ReadToEnd()
        } finally {$fd.Dispose()}
      } catch [IO.IOException] {
        # Active original GUI Worker Start-Transcript still owns the file.
        $logText=''
      }
    }
    $logSessionMatches=[int]$logText.Contains(('stop session='+$session))
    $logWorkerPidMatches=[int]$logText.Contains(('Worker initialized. PID='+$worker.Id))
    $logHasRecording=[int]$logText.Contains('GStreamer launching (EOS enabled)')
    $logReturned=[int]$logText.Contains('Record.ps1 returned; stopMarker=')
    $exited=[int]$worker.HasExited
    $exitNumber=if($worker.HasExited){[int]$worker.ExitCode}else{-999}
    Write-Output "C545D_GUI_BOOTSTRAP_DIAG,phase=$phaseValue,worker_exited=$exited,worker_exit=$exitNumber,dummy_secret_exists=$existsSecret,ready_exists=$existsReady,control_dir_exists=$controlExists,transcript_count=$logCount,mp4_count=$privateFiles,worker_cpu_ms=$workerCpuMs,ready_candidate_count=$readyCandidatesCount,ready_candidate_pid_match=$readyCandidatePidMatch,ready_candidate_name_match=$readyCandidateNameMatch,log_worker_pid_match=$logWorkerPidMatches,log_session_match=$logSessionMatches,log_has_recording=$logHasRecording,log_returned=$logReturned,real_camera=0"
    throw 'REAL_GUI_WORKER_NOT_READY'
  }
  $phase='TWO_MEDIA_MOUNTS'
  $wideRequested=0;$teleRequested=0
  for($i=0;$i -lt 420;$i++){
    Start-Sleep -Milliseconds 100
    if($worker.HasExited){break}
    $srvStream=''
    if(Test-Path -LiteralPath $svrOut){
      try {
        $fd=[IO.File]::Open($svrOut,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
        try {
          $rdr=[IO.StreamReader]::new($fd)
          $srvStream=$rdr.ReadToEnd()
        } finally {$fd.Dispose()}
      } catch [IO.IOException] {}
    }
    $wideRequested=[int]$srvStream.Contains('C545D_FINITE_RTSP_MEDIA_CONFIGURED,stream=stream1,real_camera=0')
    $teleRequested=[int]$srvStream.Contains('C545D_FINITE_RTSP_MEDIA_CONFIGURED,stream=stream6,real_camera=0')
    if($wideRequested -eq 1 -and $teleRequested -eq 1){break}
  }
  if($wideRequested -ne 1 -or $teleRequested -ne 1){throw 'REAL_WORKER_DUAL_RTSP_NOT_READY'}
  # Collect 11 isolated samples over ~31 seconds: three one-second
  # startup intervals then seven four-second intervals after warm-up.
  # Monitor ONLY our staged gst-launch and its exact worker; no passwords,
  # paths or host-wide counters are published. Do NOT interpret as leak zero.
  $resourceFirst=$null
  $resourceSteadyFirst=$null
  $resourceLast=$null
  $gioStageModuleObserved=0
  $gioModuleQueryError=0
  $ownedGstExe=[IO.Path]::GetFullPath((Join-Path $bin 'gst-launch-1.0.exe'))
  for($sampleNo=0;$sampleNo -lt 11;$sampleNo++){
    if($sampleNo -gt 0){
      $intervalMs=if($sampleNo -le 3){1000}else{4000}
      Start-Sleep -Milliseconds $intervalMs
    }
    if($worker.HasExited){throw 'WORKER_EXITED_DURING_RESOURCE_SAMPLE'}
    $gstOwned=@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue |
      Where-Object {
        try {
          $_.Path -and [string]::Equals([IO.Path]::GetFullPath($_.Path),
             $ownedGstExe,[StringComparison]::OrdinalIgnoreCase)
        } catch { $false }
      })
    if($gstOwned.Count -ne 1){throw 'OWNED_GST_RESOURCE_PROCESS_NOT_UNIQUE'}
    $gstProcess=$gstOwned[0]
    $worker.Refresh()
    $gstProcess.Refresh()
    $resourceSample=[pscustomobject]@{
      worker_private_b=[long]$worker.PrivateMemorySize64
      worker_handles=[int]$worker.HandleCount
      gst_private_b=[long]$gstProcess.PrivateMemorySize64
      gst_handles=[int]$gstProcess.HandleCount
      gst_cpu_ms=[long][Math]::Round($gstProcess.TotalProcessorTime.TotalMilliseconds)
    }
    if($sampleNo -eq 4){
      $resourceSteadyFirst=$resourceSample
      try {
        $loadedGio=@($gstProcess.Modules | Where-Object {$_.ModuleName -ieq 'gio-2.0-0.dll'})
        if($loadedGio.Count -eq 1){
          $expectedGio=Join-Path $bin 'gio-2.0-0.dll'
          $gioStageModuleObserved=[int][string]::Equals(
             [IO.Path]::GetFullPath($loadedGio[0].FileName),
             [IO.Path]::GetFullPath($expectedGio),
             [StringComparison]::OrdinalIgnoreCase)
        }
      } catch [System.ComponentModel.Win32Exception] {
        $gioModuleQueryError=1
      }
    }
    $gstProcess.Dispose()
    if($sampleNo -eq 0){$resourceFirst=$resourceSample}
    $resourceLast=$resourceSample
  }
  if($null -eq $resourceSteadyFirst -or
     $resourceFirst.worker_private_b -le 0 -or
     $resourceFirst.gst_private_b -le 0 -or
     $resourceFirst.worker_handles -le 0 -or
     $resourceFirst.gst_handles -le 0 -or
     $resourceLast.gst_cpu_ms -lt $resourceFirst.gst_cpu_ms){
    throw 'OWNED_RESOURCE_SAMPLES_INVALID'
  }
  if($worker.HasExited){throw 'WORKER_EXITED_BEFORE_CTRL_C'}
  $phase='GUI_CTRL_C_SIGNAL'
  $signalScript=(Resolve-Path -LiteralPath 'tools/Send-C545DPrivateConsoleStopCI.ps1').Path
  $ctrlCStopwatch=[Diagnostics.Stopwatch]::StartNew()
  $signalRows=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $signalScript -StageRoot $stage -WorkerPid $worker.Id -SessionId $session 2>$null)
  $signalOk='C545D_CI_GUI_CTRL_SIGNAL_PASS,stop_marker=1,console_owned=1,gst_launch_owned=1,ctrl_c_sent=1,real_camera=0'
  $signalSent=[int]($LASTEXITCODE -eq 0 -and $signalRows.Count -eq 1 -and $signalRows[0] -ceq $signalOk)
  if($signalSent -ne 1){throw 'GUI_PRIVATE_CONSOLE_SIGNAL_NOT_PROVEN'}
  $phase='WORKER_FINALIZE'
  # A 60s live RTSP fixture would otherwise end naturally. Require the
  # worker to finish promptly after the actual console Ctrl+C, not source EOF.
  if(-not $worker.WaitForExit(20000)){throw 'GUI_WORKER_EOS_NOT_TIMELY'}
  $ctrlCStopwatch.Stop()
  $stopLatencyMs=[long]$ctrlCStopwatch.ElapsedMilliseconds
  if($stopLatencyMs -gt 20000){throw 'GUI_WORKER_EOS_NOT_TIMELY'}
  Write-Output "C545D_GUI_STOP_LATENCY_STAGE,elapsed_ms=$stopLatencyMs,bounded_20s=1,real_camera=0"
  $recordExit=$worker.ExitCode
  $workerExited=1
  $transcripts=@(Get-ChildItem -LiteralPath (Join-Path $config 'Logs') -Filter 'Recording_*.txt' -File -ErrorAction SilentlyContinue)
  if($transcripts.Count -ne 1){throw 'GUI_TRANSCRIPT_NOT_UNIQUE'}
  $text=[IO.File]::ReadAllText($transcripts[0].FullName)
  $launchObserved=[int]$text.Contains('GStreamer launching (EOS enabled); attempt=1')
  $policyStop=[int]$text.Contains('Recorder exit policy: stop')
  $eosObserved=[int]$text.Contains('Recording stopped by GUI; GStreamer EOS completed.')
  $returned=[int]$text.Contains('Record.ps1 returned; stopMarker=True')
  $unexpectedReconnect=[int]$text.Contains('Recorder exit policy: reconnect')
  $nativeMatches=[regex]::Matches($text,'GStreamer returned; exitCode=(-?[0-9]+); stopMarker=(True|False)')
  $nativeExit=if($nativeMatches.Count -gt 0){[int]$nativeMatches[$nativeMatches.Count-1].Groups[1].Value}else{999}
  $markerAtReturn=[int]($nativeMatches.Count -gt 0 -and $nativeMatches[$nativeMatches.Count-1].Groups[2].Value -ceq 'True')
  $mp4=@(Get-ChildItem -LiteralPath (Join-Path $stage 'private-output') -Filter '*.mp4' -File -ErrorAction SilentlyContinue)
  $filesCount=$mp4.Count
  $mp4Bytes=if($filesCount -gt 0){[long](($mp4|Measure-Object -Property Length -Sum).Sum)}else{0}
  $mp4CountOk=if($CiSplitSeconds -eq 8){$filesCount -ge 3 -and $filesCount -le 8}else{$filesCount -eq 1}
  $stopExists=[int](Test-Path -LiteralPath $stop)
  $readyRemoved=[int](-not (Test-Path -LiteralPath $ready))
  $launchCount=[regex]::Matches($text,'GStreamer launching \(EOS enabled\); attempt=').Count
  Write-Output "C545D_GUI_WORKER_RTSP_STAGE,worker_exit=$recordExit,worker_exited=$workerExited,gui_ctrlc_sent=$signalSent,wide_mount=$wideRequested,tele_mount=$teleRequested,launch_count=$launchCount,stop_at_gst_return=$markerAtReturn,native_gst_exit=$nativeExit,policy_stop=$policyStop,policy_reconnect=$unexpectedReconnect,eos_message=$eosObserved,worker_returned=$returned,mp4_count=$filesCount,mp4_bytes=$mp4Bytes,stop_marker=$stopExists,ready_removed=$readyRemoved,real_camera=0"
  if($recordExit -ne 0 -or $signalSent -ne 1 -or
     $launchObserved -ne 1 -or $launchCount -ne 1 -or
     $markerAtReturn -ne 1 -or $nativeExit -ne 0 -or
     $policyStop -ne 1 -or $unexpectedReconnect -ne 0 -or
     $eosObserved -ne 1 -or $returned -ne 1 -or
     -not $mp4CountOk -or $mp4Bytes -lt 30000 -or
     $stopExists -ne 1 -or $readyRemoved -ne 1){
    throw 'GUI_REAL_WORKER_STOP_POLICY_FAILED'
  }
  # Confirm that the native gst process from our exact isolated bin was
  # released after GUI Ctrl+C, not merely that PowerShell Worker exited.
  $remainingStagedGst=@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue |
    Where-Object {
      try {
        $_.Path -and [string]::Equals([IO.Path]::GetFullPath($_.Path),
          $ownedGstExe,[StringComparison]::OrdinalIgnoreCase)
      } catch { $false }
    }).Count
  if($remainingStagedGst -ne 0){throw 'STAGED_GST_REMAINS_AFTER_STOP'}
  $cpuDeltaMs=[long]($resourceLast.gst_cpu_ms-$resourceFirst.gst_cpu_ms)
  Write-Output "C545D_GUI_RESOURCE_STAGE,samples=11,nominal_total_s=31,steady_window_s=24,worker_private_first_b=$($resourceFirst.worker_private_b),worker_private_last_b=$($resourceLast.worker_private_b),worker_handles_first=$($resourceFirst.worker_handles),worker_handles_last=$($resourceLast.worker_handles),gst_private_first_b=$($resourceFirst.gst_private_b),gst_private_steady_first_b=$($resourceSteadyFirst.gst_private_b),gst_private_last_b=$($resourceLast.gst_private_b),gst_handles_first=$($resourceFirst.gst_handles),gst_handles_steady_first=$($resourceSteadyFirst.gst_handles),gst_handles_last=$($resourceLast.gst_handles),gst_cpu_delta_ms=$cpuDeltaMs,gio_stage_module_observed=$gioStageModuleObserved,gio_module_query_error=$gioModuleQueryError,staged_gst_remaining=0,real_camera=0"
  $outFiles=$mp4
  $phase='MP4_VERIFY'
  # Every accelerated fragment must be independently finalized and decodable.
  # Confirm splitmux numeric suffixes 00000..N without gaps or duplicates.
  if($CiSplitSeconds -eq 8){
    $indices=@()
    foreach($f in $outFiles){
      if($f.Name -cnotmatch '_([0-9]{5})\.mp4$'){throw 'CI_SPLIT_FILENAME_INVALID'}
      $indices += [int]$Matches[1]
    }
    $indices=@($indices | Sort-Object)
    for($i=0;$i -lt $indices.Count;$i++){
      if($indices[$i] -ne $i){throw 'CI_SPLIT_SEQUENCE_INVALID'}
    }
  }
  foreach($f in $outFiles){
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
  }
  $mp4Decoded=1
  if($CiSplitSeconds -eq 8){
    # Run the REAL, unmodified event-driven SegmentNamerWorker.ps1 after
    # the four test fragments were individually decoded. It watches only
    # disposable copies in a private fixture, never the original outputs.
    $phase='SEGMENT_NAMER'
    $namerTest=(Resolve-Path -LiteralPath 'tests/Assert-C545DSegmentNamerClosedMp4CI.ps1').Path
    $namerTokens=$null;$namerParseErrors=$null
    [void][Management.Automation.Language.Parser]::ParseFile(
      $namerTest,[ref]$namerTokens,[ref]$namerParseErrors)
    if($namerParseErrors.Count -gt 0){throw 'CI_NAMER_SYNTAX'}
    $namerRows=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $namerTest -StageRoot $stage -SampleMp4 $outFiles[0].FullName 2>$null)
    foreach($nr in $namerRows){
      if(([string]$nr) -cmatch '^C545D_SEGMENT_NAMER_CI,ready=[01],locked_deferred=[01],renamed=[0-9]+,mp4_hashes_intact=[01],manual_preserved=[01],clean_exit=[01],source_unchanged=[01],real_camera=0,host_modified=0,reason=[A-Z_]+$'){
        Write-Output $nr
      }
    }
    $namerExpected='C545D_SEGMENT_NAMER_CI,ready=1,locked_deferred=1,renamed=4,mp4_hashes_intact=1,manual_preserved=1,clean_exit=1,source_unchanged=1,real_camera=0,host_modified=0,reason=PASS'
    if($LASTEXITCODE -ne 0 -or $namerRows.Count -ne 1 -or $namerRows[0] -cne $namerExpected){
      throw 'CI_NAMER_GATE_FAILED'
    }
  }
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
    'ORIGINAL_BYTES_CHANGED','EARLY_WORKER_MARKER','GUI_WORKER_MIRROR_NOT_EXACT',
    'REAL_GUI_WORKER_NOT_READY','REAL_WORKER_DUAL_RTSP_NOT_READY',
    'WORKER_EXITED_BEFORE_CTRL_C','GUI_PRIVATE_CONSOLE_SIGNAL_NOT_PROVEN',
    'GUI_WORKER_FINALIZE_TIMEOUT','GUI_WORKER_EOS_NOT_TIMELY','GUI_TRANSCRIPT_NOT_UNIQUE',
    'GUI_REAL_WORKER_STOP_POLICY_FAILED',
    'WORKER_EXITED_DURING_RESOURCE_SAMPLE',
    'OWNED_GST_RESOURCE_PROCESS_NOT_UNIQUE',
    'OWNED_RESOURCE_SAMPLES_INVALID','STAGED_GST_REMAINS_AFTER_STOP',
    'CI_SPLIT_ANCHOR_NOT_UNIQUE','CI_SPLIT_MIRROR_NOT_REVERSIBLE',
    'CI_SPLIT_SOURCE_SYNTAX','CI_SPLIT_FILENAME_INVALID','CI_SPLIT_SEQUENCE_INVALID',
    'CI_NAMER_SYNTAX','CI_NAMER_GATE_FAILED')
  $reason=if($_.Exception.Message -in $known){$_.Exception.Message}else{'BLOCKED'}
  Write-Output "C545D_GUI_WORKER_RTSP_FAIL,phase=$phase,reason=$reason,real_camera=0,host_modified=0"
  throw 'SANITIZED_CI_LOOPBACK_RECORD_TEST_FAILED'
} finally {
  if($worker){
    if(-not $worker.HasExited){
      # CI-only failure cleanup of process we personally started.
      try {$worker.Kill();[void]$worker.WaitForExit(4000)}catch {}
    }
    $worker.Dispose()
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
if($phase -cne 'PASS' -or $mp4Decoded -ne 1 -or $eosObserved -ne 1 -or $signalSent -ne 1){
  throw 'GUI_CTRL_C_EOS_NOT_QUALIFIED'
}
if($CiSplitSeconds -eq 8){
  Write-Output "C545D_GUI_ACCELERATED_SPLIT_CI_PASS,original_worker=1,ci_modified_split_only=1,synthetic_rtsp=1,fragments=$filesCount,each_mp4_decoded=1,gui_ctrlc_eos=1,owned_rollback=1,real_hourly_split_tested=0,real_camera=0,install_approved=0"
} else {
  Write-Output 'C545D_GUI_WORKER_REAL_SOURCE_CTRL_C_CI_PASS,original_worker=1,original_recorder_mirror=1,two_local_rtsp=1,gui_ctrlc_event=1,worker_survived=1,gst_eos=1,mp4_h264_aac_decoded=1,owned_rollback=1,real_camera=0,real_hourly_split_tested=0,install_approved=0'
}
