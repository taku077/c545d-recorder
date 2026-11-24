#Requires -Version 5.1
<#
 CI-only genuine WinForms GUI START/STOP integration (not a visible mouse).
 Original unmodified GUI event handlers launch original RecordGUIWorker.ps1,
 CI-private Record.ps1 and the actual original SegmentNamerWorker.ps1.
 Two synthetic localhost RTSP streams; exact pinned candidate Gio; 8-second
 CI-only split. Actual GUI button click calls Ctrl+C/EOS; no production host,
 real camera, real 3600s split, registry or installed DLL mutation.
 Never run outside disposable GitHub hosted Windows test runner.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SdkRoot,
  [Parameter(Mandatory=$true)][string]$CandidateDll,
  [Parameter(Mandatory=$true)][string]$ReferenceManifest,
  [ValidateSet(8)][int]$CiSplitSeconds=8,
  [ValidateSet(0,1000,5000)][int]$CiPreStopDelayMs=0,
  [string]$CiMetadataProbeExe,
  [string]$CiMetadataProbeSha256
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
$CiLiveNamer=$true
$liveNamer=$null;$liveNamerStop='';$liveNamerReady=0;$liveRenamedBeforeStop=0
$liveNamerClosed=0;$liveRenameCount=0
$gui=$null;$guiStopMarker='';$guiQuitMarker='';$guiStarted=0;$guiStop=0;$guiExit=0
$namerOwned=$null;$namerExit=-999
$workerExitMismatch=0;$mediaVerified=0
try {
  if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
     -not $env:RUNNER_TEMP){throw 'NOT_DISPOSABLE_WINDOWS_CI'}
  if($CiLiveNamer -and $CiSplitSeconds -ne 8){throw 'LIVE_NAMER_REQUIRES_CI_SPLIT'}
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
  $namerSource=(Resolve-Path -LiteralPath 'SegmentNamer.ps1').Path
  $namerWorkerSource=(Resolve-Path -LiteralPath 'SegmentNamerWorker.ps1').Path
  foreach($src in @($source,$settings,$CandidateDll,$workerSource,$guiSource,$namerSource,$namerWorkerSource)){
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
      'GST_PLUGIN_SYSTEM_PATH','GST_PLUGIN_SYSTEM_PATH_1_0','C545D_METADATA_V04','C545D_METADATA_PROBE_SHA256')){
    $prior[$key]=[Environment]::GetEnvironmentVariable($key,'Process')
  }
  $env:PATH="$bin;$sdkBin;$($prior['PATH'])"
  # All existing invocations remain explicitly OFF. Only the separate CI gate
  # supplies a direct binary from the pinned, archive-verified fixture.
  Remove-Item Env:C545D_METADATA_V04,Env:C545D_METADATA_PROBE_SHA256 -ErrorAction SilentlyContinue
  $ciMetaEnabled=[bool]$CiMetadataProbeExe
  if($ciMetaEnabled){
    $probeItem=Get-Item -LiteralPath $CiMetadataProbeExe -ErrorAction Stop
    if($probeItem.PSIsContainer -or $probeItem.Name -cne 'ffprobe.exe' -or
       $CiMetadataProbeSha256 -notmatch '\A[0-9A-Fa-f]{64}\z' -or
       (Get-FileHash -LiteralPath $probeItem.FullName).Hash -ine $CiMetadataProbeSha256){
      throw 'CI_METADATA_PROBE_IDENTITY'
    }
    $env:PATH=$probeItem.DirectoryName+';'+$env:PATH
    if((Get-Command ffprobe.exe -ErrorAction Stop).Source -ine $probeItem.FullName){throw 'CI_METADATA_PROBE_RESOLUTION'}
    $env:C545D_METADATA_V04='1'
    $env:C545D_METADATA_PROBE_SHA256=$CiMetadataProbeSha256
  }elseif($CiMetadataProbeSha256){throw 'CI_METADATA_PARTIAL_OPTIN'}
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
    output_folder=(Join-Path $stage 'private-output')
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
  # The GUI itself starts its unchanged namer when the WinForms app opens.
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
  $phase='GUI_BOOTSTRAP'
  $uiSourceText=[IO.File]::ReadAllText($guiSource)
  $uiAnchor='[void][System.Windows.Forms.Application]::Run($form)'
  if([regex]::Matches($uiSourceText,[regex]::Escape($uiAnchor)).Count -ne 1){
    throw 'GUI_SOURCE_INSERTION_UNSAFE'
  }
  # A bounded timer on the *actual WinForms GUI thread* invokes the exact
  # existing Start/Stop/Quit Click handlers, not a second reimplementation.
  $uiHook=@'
$script:ciWinFormsStartTime=Get-Date
$script:ciWinFormsPhase=0
$script:ciWinFormsStopRequested=0
$script:ciWinFormsTime=New-Object System.Windows.Forms.Timer
$script:ciWinFormsTime.Interval=200
$script:ciWinFormsTime.Add_Tick({
  try {
    if(((Get-Date)-$script:ciWinFormsStartTime).TotalSeconds -gt 155){
      throw 'CI_GUI_SESSION_TIMEOUT'
    }
    $root=$PSScriptRoot
    if([IO.File]::ReadAllText((Join-Path $root '.c545d-ci-owned')) -cne
       'CI_MIRROR_ONLY_NOT_FOR_EXECUTION'){throw 'CI_GUI_OWNER_INVALID'}
    switch($script:ciWinFormsPhase){
      0 {
        if(([string]$txtIP.Text).Trim() -cne '127.0.0.1' -or
           ([string]$txtOutput.Text).Trim() -cne (Join-Path $root 'private-output') -or
           -not $btnStart.Enabled){throw 'CI_GUI_SETTINGS_NOT_PRIVATE'}
        $btnStart.PerformClick()
        if(-not (Is-Recording)){throw 'CI_GUI_START_FAILED'}
        if(-not $script:namerReadyFile -or
           -not (Test-Path -LiteralPath $script:namerReadyFile -PathType Leaf)){
           throw 'CI_GUI_NAMER_NOT_READY'
        }
        $script:ciWinFormsPhase=1
        $id=[string]$script:sessionId
        # $PID is a read-only automatic variable in PowerShell (case insensitive).
        $launchedWorkerPid=[int]$script:worker.Id
        if($id -cnotmatch '^[a-f0-9]{32}$' -or $launchedWorkerPid -le 0){
          throw 'CI_GUI_SESSION_INVALID'
        }
        [IO.File]::WriteAllText((Join-Path $root 'ci-gui-session'),($id+','+$launchedWorkerPid))
      }
      1 {
        if(-not (Test-Path -LiteralPath (Join-Path $root 'ci-gui-request-stop') -PathType Leaf)){break}
        $btnStop.PerformClick()
        if(-not $script:stopRequested -or $script:stopSignalFailed -or
           -not (Test-Path -LiteralPath $script:stopFile -PathType Leaf)){
          throw 'CI_GUI_CTRL_C_NOT_SENT'
        }
        [IO.File]::WriteAllText((Join-Path $root 'ci-gui-stop-ok'),'STOP_MARKER_AND_GUI_CTRL_C')
        $script:ciWinFormsPhase=2
      }
      2 {
        if(-not (Test-Path -LiteralPath (Join-Path $root 'ci-gui-allow-quit') -PathType Leaf)){break}
        if(Is-Recording){break}
        if(-not $btnQuit.Enabled){throw 'CI_GUI_QUIT_DISABLED'}
        [IO.File]::WriteAllText((Join-Path $root 'ci-gui-quit-ok'),'WINFORMS_QUIT_CLICKED')
        $btnQuit.PerformClick()
        $script:ciWinFormsPhase=3
      }
    }
  } catch {
    $id=[string]$_.Exception.Message
    $codes=@('CI_GUI_SESSION_TIMEOUT','CI_GUI_OWNER_INVALID','CI_GUI_SETTINGS_NOT_PRIVATE',
      'CI_GUI_START_FAILED','CI_GUI_NAMER_NOT_READY','CI_GUI_SESSION_INVALID',
      'CI_GUI_CTRL_C_NOT_SENT','CI_GUI_QUIT_DISABLED')
    if($id -notin $codes){$id='CI_GUI_UNCLASSIFIED'}
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'ci-gui-failure'),$id)
    # No forced worker termination; failure must be reported to outer CI.
    $script:ciWinFormsPhase=4
    $script:allowExit=$true
    $form.Close()
  }
})
$script:ciWinFormsTime.Start()
'@
  $guiPrivate=$uiSourceText.Replace($uiAnchor,$uiHook+[Environment]::NewLine+$uiAnchor)
  if($guiPrivate.Replace($uiHook+[Environment]::NewLine+$uiAnchor,$uiAnchor) -cne $uiSourceText){
    throw 'GUI_SOURCE_ROUNDTRIP_MISMATCH'
  }
  $tok=$null;$parseErr=$null
  [void][Management.Automation.Language.Parser]::ParseInput($guiPrivate,[ref]$tok,[ref]$parseErr)
  if($parseErr.Count -ne 0){throw 'GUI_CI_SOURCE_SYNTAX'}
  # Retain BOM for WinPS5.1 Japanese messages (otherwise ACP decoding).
  [IO.File]::WriteAllText((Join-Path $stage 'C545D_App.ps1'),$guiPrivate,
    (New-Object System.Text.UTF8Encoding($true)))
  foreach($path in @($namerSource,$namerWorkerSource)){
    $target=Join-Path $stage ([IO.Path]::GetFileName($path))
    Copy-Item -LiteralPath $path -Destination $target
    if((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -cne $snapshot[$path]){
      throw 'GUI_NAMER_SOURCE_CHANGED'
    }
  }
  if($ciMetaEnabled){
    $metaStage=Join-Path $stage 'diagnostics'
    New-Item -ItemType Directory -Path $metaStage | Out-Null
    foreach($name in @('C545D-MetadataIntegrationV04.ps1','C545D-MetadataClassifierV04.ps1',
        'C545DClosedProbeV04.cs','C545DMetadataJournalV04.cs','C545DMetadataWriterV04.cs')){
      $src=(Resolve-Path -LiteralPath (Join-Path 'diagnostics' $name)).Path
      $snapshot[$src]=(Get-FileHash -LiteralPath $src).Hash
      $target=Join-Path $metaStage $name
      Copy-Item -LiteralPath $src -Destination $target
      if((Get-FileHash -LiteralPath $target).Hash -cne $snapshot[$src]){throw 'CI_METADATA_MODULE_CHANGED'}
    }
  }
  # Bootstrap only private synthetic settings & DPAPI in the actual GUI
  # process, so the genuine child recorder decrypts using the same token.
  $guiBootstrap=@'
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
   [IO.File]::ReadAllText((Join-Path $root '.c545d-ci-owned')) -cne
     'CI_MIRROR_ONLY_NOT_FOR_EXECUTION'){exit 3}
$env:LOCALAPPDATA=Join-Path $root 'ci-localappdata'
$cfg=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer'
$secret=Join-Path $cfg 'camera_password.dpapi'
if(Test-Path -LiteralPath $secret){exit 3}
$pass=ConvertTo-SecureString 'CI_SYNTHETIC_NOT_REAL' -AsPlainText -Force
$encrypted=ConvertFrom-SecureString $pass
[IO.File]::WriteAllText($secret,$encrypted,[Text.Encoding]::ASCII)
[IO.File]::WriteAllText((Join-Path $root 'ci-gui-bootstrap-ok'),'DPAPI_PRIVATE')
& (Join-Path $root 'C545D_App.ps1')
'@
  $bootstrap=Join-Path $stage 'ci-winforms-bootstrap.ps1'
  [IO.File]::WriteAllText($bootstrap,$guiBootstrap,(New-Object System.Text.UTF8Encoding($false)))
  $phase='GUI_START'
  $previousModulePath=[Environment]::GetEnvironmentVariable('PSModulePath','Process')
  try {
    [Environment]::SetEnvironmentVariable('PSModulePath',$null,'Process')
    $gui=Start-Process -FilePath $ps -ArgumentList @(
      '-NoLogo','-NoProfile','-STA','-ExecutionPolicy','Bypass',
      '-File',('"'+$bootstrap+'"')
    ) -WorkingDirectory $stage -WindowStyle Hidden -PassThru
  } finally {
    [Environment]::SetEnvironmentVariable('PSModulePath',$previousModulePath,'Process')
  }
  $sessionFile=Join-Path $stage 'ci-gui-session'
  $ciGuiFailure=Join-Path $stage 'ci-gui-failure'
  for($i=0;$i -lt 200;$i++){
    if($gui.HasExited -or (Test-Path -LiteralPath $ciGuiFailure -PathType Leaf)){break}
    if(Test-Path -LiteralPath $sessionFile -PathType Leaf){break}
    Start-Sleep -Milliseconds 100
  }
  if(-not (Test-Path -LiteralPath $sessionFile -PathType Leaf)){
    if(Test-Path -LiteralPath $ciGuiFailure){
      $reason=[IO.File]::ReadAllText($ciGuiFailure)
      if($reason -cmatch '^CI_GUI_[A-Z_]+$'){Write-Output ('C545D_GUI_INTEGRATED_DIAG,code='+$reason+',real_camera=0')}
    }
    throw 'GUI_CI_DID_NOT_START_WORKER'
  }
  $pair=([IO.File]::ReadAllText($sessionFile).Trim()).Split(',')
  if($pair.Count -ne 2 -or $pair[0] -cnotmatch '^[a-f0-9]{32}$' -or
    $pair[1] -cnotmatch '^[0-9]{1,10}$'){throw 'GUI_CI_SESSION_INVALID'}
  $session=$pair[0]
  $childPID=[int]$pair[1]
  $childInfo=Get-CimInstance Win32_Process -Filter ("ProcessId = "+$childPID)
  if(-not $childInfo -or [int]$childInfo.ParentProcessId -ne $gui.Id -or
      -not [string]::Equals([IO.Path]::GetFullPath([string]$childInfo.ExecutablePath),
          [IO.Path]::GetFullPath($ps),[StringComparison]::OrdinalIgnoreCase)){
    throw 'GUI_CI_WORKER_NOT_OWNED'
  }
  $worker=Get-Process -Id $childPID -ErrorAction Stop
  $stop=Join-Path $control ('session_'+$session+'.stop')
  $ready=Join-Path $control ('session_'+$session+'.ready')
  $phase='GUI_WORKER_READY'
  $readySeen=$false
  for($i=0;$i -lt 300;$i++){
    Start-Sleep -Milliseconds 100
    if($worker.HasExited -or $gui.HasExited){break}
    if(Test-Path -LiteralPath $ready){
      try {$readySeen=([IO.File]::ReadAllText($ready).Trim() -ceq [string]$worker.Id)}
      catch [IO.IOException] {}
      if($readySeen){break}
    }
  }
  $namerReadyFiles=@(Get-ChildItem -LiteralPath $control -Filter 'namer_*.ready' -File -ErrorAction Stop)
  $liveNamerReady=[int]($namerReadyFiles.Count -eq 1)
  if(-not $readySeen -or $liveNamerReady -ne 1 -or
      -not (Test-Path -LiteralPath (Join-Path $stage 'ci-gui-bootstrap-ok'))){
    throw 'GUI_CI_WORKER_NOT_READY'
  }
  # The .ready marker alone does not prove actual watcher process lifetime.
  # Verify a SINGLE WinPS child, owned by this exact CI-private GUI, whose
  # command line references only our private unmodified namer script.
  $phase='GUI_NAMER_PROCESS_OWNERSHIP'
  $expectedNamerScript=[IO.Path]::GetFullPath((Join-Path $stage 'SegmentNamerWorker.ps1'))
  $expectedWinPs=[IO.Path]::GetFullPath($ps)
  $namerOwnedCandidates=@(Get-CimInstance Win32_Process -Filter ("ParentProcessId = "+$gui.Id) |
    Where-Object {
      $exePath=[string]$_.ExecutablePath
      $cmd=[string]$_.CommandLine
      $exePath -and [string]::Equals([IO.Path]::GetFullPath($exePath),
        $expectedWinPs,[StringComparison]::OrdinalIgnoreCase) -and
      $cmd.IndexOf($expectedNamerScript,[StringComparison]::OrdinalIgnoreCase) -ge 0
    })
  if($namerOwnedCandidates.Count -ne 1){throw 'GUI_CI_NAMER_PROCESS_NOT_UNIQUE'}
  $namerOwned=Get-Process -Id ([int]$namerOwnedCandidates[0].ProcessId) -ErrorAction Stop
  if($namerOwned.HasExited){throw 'GUI_CI_NAMER_PROCESS_EARLY_EXIT'}
  $guiStarted=1
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
    if($CiLiveNamer){
      if($gui.HasExited -or (Test-Path -LiteralPath $ciGuiFailure)){throw 'GUI_CI_EXITED_DURING_RECORDING'}
      $renamedNow=@(Get-ChildItem -LiteralPath (Join-Path $stage 'private-output') -Filter '*.mp4' -File -ErrorAction Stop |
        Where-Object {$_.Name -cmatch '^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}_\d{2}-\d{2}(?:_\d{2})?\.mp4$'})
      if($renamedNow.Count -gt 0){$liveRenamedBeforeStop=1}
    }
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
  # Vary only the temporal alignment of the STOP click relative to splitmux
  # fragments; original production GUI/worker/recorder source is untouched.
  # The finite synthetic RTSP fixture runs for ~60s, so bounded +5s stays
  # within the test's 31s sampling window plus startup/cleanup allowance.
  $phase='CI_PRE_STOP_ALIGNMENT'
  if($CiPreStopDelayMs -gt 0){
    Start-Sleep -Milliseconds $CiPreStopDelayMs
    if($worker.HasExited -or $gui.HasExited){
      throw 'CI_STOP_ALIGNMENT_WORKER_EXITED'
    }
  }
  Write-Output "C545D_GUI_STOP_ALIGNMENT_CI,delay_ms=$CiPreStopDelayMs,original_source_unchanged=1,synthetic_rtsp=1,real_camera=0"
  $phase='GUI_STOP_BUTTON_CLICK'
  $ctrlCStopwatch=[Diagnostics.Stopwatch]::StartNew()
  [IO.File]::WriteAllText((Join-Path $stage 'ci-gui-request-stop'),'CI_ONLY_STOP_CLICK')
  $guiStopMarker=Join-Path $stage 'ci-gui-stop-ok'
  for($i=0;$i -lt 140;$i++){
    if($gui.HasExited -or (Test-Path -LiteralPath $ciGuiFailure)){break}
    if(Test-Path -LiteralPath $guiStopMarker -PathType Leaf){break}
    Start-Sleep -Milliseconds 100
  }
  $signalSent=[int]((Test-Path -LiteralPath $guiStopMarker -PathType Leaf) -and
    [IO.File]::ReadAllText($guiStopMarker) -ceq 'STOP_MARKER_AND_GUI_CTRL_C')
  $guiStop=$signalSent
  if($signalSent -ne 1){throw 'GUI_CI_STOP_BUTTON_FAILED'}
  $phase='WORKER_FINALIZE'
  # A 60s live RTSP fixture would otherwise end naturally. Require the
  # worker to finish promptly after the actual console Ctrl+C, not source EOF.
  if(-not $worker.WaitForExit(20000)){throw 'GUI_WORKER_EOS_NOT_TIMELY'}
  $ctrlCStopwatch.Stop()
  $stopLatencyMs=[long]$ctrlCStopwatch.ElapsedMilliseconds
  if($stopLatencyMs -gt 20000){throw 'GUI_WORKER_EOS_NOT_TIMELY'}
  $recordExit=[int]$worker.ExitCode
  # Preserve the raw 32-bit Windows status even for negative signed exit
  # codes. A lost old code cannot be reconstructed from EOS success alone.
  # This pure-number diagnostic does not weaken any existing stop assertion.
  $recordExitUInt=[BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$recordExit),0)
  $recordExitHex=[string]::Format('{0:X8}',$recordExitUInt)
  $controlCRef=[BitConverter]::ToUInt32([BitConverter]::GetBytes([int]-1073741510),0)
  if([string]::Format('{0:X8}',$controlCRef) -cne 'C000013A'){
    throw 'CI_EXIT_HEX_ENCODING_FAILED'
  }
  Write-Output "C545D_GUI_WORKER_EXIT_HEX_CI,signed=$recordExit,hex=$recordExitHex,after_wait=1,real_camera=0"
  # This record is emitted BEFORE later MP4/GUI checks and can identify a
  # nonzero worker status even if an inner cleanup later prevents failure logs.
  Write-Output "C545D_GUI_STOP_LATENCY_STAGE,elapsed_ms=$stopLatencyMs,worker_exit=$recordExit,bounded_20s=1,real_camera=0"
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
  # Original worker/recorder already log Windows console handler counters.
  # Publish only bounded scalar counts, never the transcript or sensitive
  # host paths, private camera settings, or credential-bearing process args.
  $nativeCtrlCLog=[regex]::Matches($text,'GStreamer returned; exitCode=-?[0-9]+; stopMarker=(?:True|False); consoleCtrlCEvents=([0-9]+)')
  $pendingCtrlCLog=[regex]::Matches($text,'Record\.ps1 returned; stopMarker=(?:True|False); pendingCtrlCEvents=([0-9]+)')
  $workerConsoleEventsAtGst=-1
  $workerConsoleEventsPending=-1
  if($nativeCtrlCLog.Count -gt 0){
    $workerConsoleEventsAtGst=[int]$nativeCtrlCLog[$nativeCtrlCLog.Count-1].Groups[1].Value
  }
  if($pendingCtrlCLog.Count -gt 0){
    $workerConsoleEventsPending=[int]$pendingCtrlCLog[$pendingCtrlCLog.Count-1].Groups[1].Value
  }
  Write-Output "C545D_GUI_CONSOLE_HANDLER_STAGE,events_at_gst_return=$workerConsoleEventsAtGst,events_pending_after_record=$workerConsoleEventsPending,worker_exit=$recordExit,real_camera=0"
  if($CiLiveNamer){
    $phase='LIVE_NAMER_DRAIN'
    $finalRx='^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}_\d{2}-\d{2}(?:_\d{2})?\.mp4$'
    $livePending=999
    for($i=0;$i -lt 280;$i++){
      if($gui.HasExited){throw 'GUI_CI_EXITED_BEFORE_MP4_DRAIN'}
      $liveItems=@(Get-ChildItem -LiteralPath (Join-Path $stage 'private-output') -Filter '*.mp4' -File -ErrorAction Stop)
      $liveFinal=@($liveItems | Where-Object {$_.Name -cmatch $finalRx})
      $livePending=@($liveItems | Where-Object {$_.Name -notmatch $finalRx}).Count
      if($liveFinal.Count -ge 3 -and $liveFinal.Count -le 8 -and $livePending -eq 0){break}
      Start-Sleep -Milliseconds 100
    }
    $liveRenameCount=$liveFinal.Count
    if($liveRenamedBeforeStop -ne 1){throw 'LIVE_NAMER_NOT_DURING_RECORDING'}
    if($liveRenameCount -lt 3 -or $liveRenameCount -gt 8 -or $livePending -ne 0){
      throw 'LIVE_NAMER_NOT_FULLY_DRAINED'
    }
    $renameLog=Join-Path $config 'Logs\Filename_Rename.log'
    if(-not (Test-Path -LiteralPath $renameLog -PathType Leaf)){
      throw 'LIVE_NAMER_LOG_MISSING'
    }
    $renameText=[IO.File]::ReadAllText($renameLog)
    $entries=[regex]::Matches($renameText,'Renamed \(closed\): (\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d-\d{3}_(\d{5})\.mp4) -> ')
    $seq=@($entries | ForEach-Object {[int]$_.Groups[2].Value} | Sort-Object)
    if($entries.Count -ne $liveRenameCount){throw 'LIVE_NAMER_LOG_SEQUENCE'}
    for($i=0;$i -lt $seq.Count;$i++){
      if($seq[$i] -ne $i){throw 'LIVE_NAMER_LOG_SEQUENCE'}
    }
  }
  $mp4=@(Get-ChildItem -LiteralPath (Join-Path $stage 'private-output') -Filter '*.mp4' -File -ErrorAction SilentlyContinue)
  $filesCount=$mp4.Count
  $mp4Bytes=if($filesCount -gt 0){[long](($mp4|Measure-Object -Property Length -Sum).Sum)}else{0}
  $mp4CountOk=if($CiSplitSeconds -eq 8){$filesCount -ge 3 -and $filesCount -le 8}else{$filesCount -eq 1}
  $stopExists=[int](Test-Path -LiteralPath $guiStopMarker)
  $readyRemoved=[int](-not (Test-Path -LiteralPath $ready))
  $launchCount=[regex]::Matches($text,'GStreamer launching \(EOS enabled\); attempt=').Count
  Write-Output "C545D_GUI_WORKER_RTSP_STAGE,worker_exit=$recordExit,worker_exited=$workerExited,gui_ctrlc_sent=$signalSent,wide_mount=$wideRequested,tele_mount=$teleRequested,launch_count=$launchCount,stop_at_gst_return=$markerAtReturn,native_gst_exit=$nativeExit,policy_stop=$policyStop,policy_reconnect=$unexpectedReconnect,eos_message=$eosObserved,worker_returned=$returned,mp4_count=$filesCount,mp4_bytes=$mp4Bytes,stop_marker=$stopExists,ready_removed=$readyRemoved,real_camera=0"
  # Split the exact same acceptance predicate into individual fail-closed
  # codes; CI prints only the first failed invariant, never camera log content.
  $phase='GUI_STOP_POLICY_CHECK'
  # Do not ignore the nonzero worker status. Continue private media and GUI
  # cleanup checks and fail at the end, to identify whether EOS MP4s survived.
  $workerExitMismatch=[int]($recordExit -ne 0)
  if($signalSent -ne 1){throw 'GUI_STOP_POLICY_NO_SIGNAL'}
  if($launchObserved -ne 1){throw 'GUI_STOP_POLICY_NOT_LAUNCHED'}
  if($launchCount -ne 1){throw 'GUI_STOP_POLICY_LAUNCH_COUNT'}
  if($markerAtReturn -ne 1){throw 'GUI_STOP_POLICY_MARKER_AT_RETURN'}
  if($nativeExit -ne 0){throw 'GUI_STOP_POLICY_GST_EXIT'}
  if($policyStop -ne 1){throw 'GUI_STOP_POLICY_STOP_DECISION'}
  if($unexpectedReconnect -ne 0){throw 'GUI_STOP_POLICY_RECONNECT'}
  if($eosObserved -ne 1){throw 'GUI_STOP_POLICY_EOS_MISSING'}
  if($returned -ne 1){throw 'GUI_STOP_POLICY_RECORD_RETURN'}
  if(-not $mp4CountOk){throw 'GUI_STOP_POLICY_FRAGMENT_COUNT'}
  if($mp4Bytes -lt 30000){throw 'GUI_STOP_POLICY_MP4_BYTES'}
  if($stopExists -ne 1){throw 'GUI_STOP_POLICY_MARKER_PROOF'}
  if($readyRemoved -ne 1){throw 'GUI_STOP_POLICY_WORKER_READY_LEFT'}
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
  if($CiSplitSeconds -eq 8 -and -not $CiLiveNamer){
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
  if($CiSplitSeconds -eq 8 -and -not $CiLiveNamer){
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
  if($CiLiveNamer){
    $phase='GUI_QUIT_BUTTON_CLICK'
    [IO.File]::WriteAllText((Join-Path $stage 'ci-gui-allow-quit'),'VERIFIED_EOS_AND_MP4')
    $guiQuitMarker=Join-Path $stage 'ci-gui-quit-ok'
    if(-not $gui.WaitForExit(22000)){throw 'GUI_CI_QUIT_TIMEOUT'}
    $guiExit=[int]((Test-Path -LiteralPath $guiQuitMarker -PathType Leaf) -and
      [IO.File]::ReadAllText($guiQuitMarker) -ceq 'WINFORMS_QUIT_CLICKED')
    if($guiExit -ne 1 -or $gui.ExitCode -ne 0){throw 'GUI_CI_QUIT_CLICK_FAILED'}
    $readyRemain=1
    for($i=0;$i -lt 120;$i++){
      $readyRemain=@(Get-ChildItem -LiteralPath $control -Filter 'namer_*.ready' -File -ErrorAction Stop).Count
      if($readyRemain -eq 0){break}
      Start-Sleep -Milliseconds 100
    }
    if($readyRemain -ne 0){throw 'GUI_CI_NAMER_NOT_CLOSED'}
    if(-not $namerOwned.WaitForExit(15000)){
      throw 'GUI_CI_NAMER_PROCESS_NOT_EXITED'
    }
    $namerExit=[int]$namerOwned.ExitCode
    if($namerExit -ne 0){throw 'GUI_CI_NAMER_PROCESS_BAD_EXIT'}
    Write-Output "C545D_GUI_NAMER_PROCESS_STAGE,owned=1,process_exited=1,exit_code=$namerExit,ready_removed=1,real_camera=0"
    $liveNamerClosed=1
  }
  foreach($src in $snapshot.Keys){
    if((Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash -cne $snapshot[$src]){
      throw 'ORIGINAL_BYTES_CHANGED'
    }
  }
  $phase='CI_METADATA_REPORT'
  $metaRoot=Join-Path $localData 'C545D_GStreamer\MetadataV04'
  if($ciMetaEnabled){
    $j=@(Get-ChildItem -LiteralPath (Join-Path $metaRoot 'journal') -File)
    $receipts=@(Get-ChildItem -LiteralPath (Join-Path $metaRoot 'receipts') -File)
    if($j.Count -ne 1 -or $receipts.Count -ne 1){throw 'CI_METADATA_FILE_COUNT'}
    $journalRows=@(Get-Content -LiteralPath $j[0].FullName)
    if($journalRows.Count -ne ($liveRenameCount+1) -or $journalRows[0] -cnotmatch '^C545D_META_V1\|\d{8}$'){
      throw 'CI_METADATA_ROW_COUNT'
    }
    foreach($row in @($journalRows|Select-Object -Skip 1)){
      if($row -cnotmatch '\|profile_match_metadata_only\|'){throw 'CI_METADATA_PROFILE'}
    }
    $receiptRows=@(Get-Content -LiteralPath $receipts[0].FullName)
    $expected='^END\|\d{8}T\d{6}\.\d{7}Z\|'+$liveRenameCount+'\|0\|'+$liveRenameCount+'\|0\|0$'
    if($receiptRows.Count -ne 2 -or $receiptRows[0] -cnotmatch '^C545D_WRITER_V1\|\d{8}T\d{6}\.\d{7}Z\|[0-9a-f]{32}$' -or
       $receiptRows[1] -cnotmatch $expected){throw 'CI_METADATA_RECEIPT'}
    $released=[IO.File]::Open((Join-Path $metaRoot 'writer.lease'),[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    $released.Dispose()
    Write-Output "C545D_GUI_METADATA_ENABLED_CI_PASS,renamed=$liveRenameCount,rows=$liveRenameCount,receipt=1,lease_released=1,all_decoded=$mp4Decoded,real_camera=0,install_approved=0"
  }elseif(Test-Path -LiteralPath $metaRoot){throw 'CI_METADATA_DEFAULT_OFF_CHANGED'}
  $mediaVerified=1
  if($workerExitMismatch -eq 1){
    $phase='POST_VERIFICATION_WORKER_STATUS'
    throw 'GUI_STOP_POLICY_WORKER_EXIT'
  }
  Write-Output "C545D_WINFORMS_REAL_RECORDING_CI_PASS,gui_start_click=$guiStarted,gui_stop_click=$guiStop,gui_quit_click=$guiExit,namer_ready=$liveNamerReady,renamed_before_stop=$liveRenamedBeforeStop,renamed_total=$liveRenameCount,all_decoded=$mp4Decoded,gui_ctrl_c_eos=$signalSent,watcher_closed=$liveNamerClosed,source_unchanged=1,real_rtsp=0,synthetic_rtsp=1,real_camera=0,install_approved=0"
  $phase='PASS'
} catch {
  $known=@('CI_METADATA_PROBE_IDENTITY','CI_METADATA_PROBE_RESOLUTION','CI_METADATA_PARTIAL_OPTIN','CI_METADATA_MODULE_CHANGED','CI_METADATA_FILE_COUNT','CI_METADATA_ROW_COUNT','CI_METADATA_PROFILE','CI_METADATA_RECEIPT','CI_METADATA_DEFAULT_OFF_CHANGED','NOT_DISPOSABLE_WINDOWS_CI','UNSAFE_CI_TEMP','REFERENCE_NOT_PINNED',
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
    'CI_NAMER_SYNTAX','CI_NAMER_GATE_FAILED',
    'LIVE_NAMER_REQUIRES_CI_SPLIT','LIVE_NAMER_MARKER_COLLISION',
    'LIVE_NAMER_OUTPUT_MISSING','LIVE_NAMER_NOT_READY','LIVE_NAMER_EARLY_EXIT',
    'LIVE_NAMER_NOT_DURING_RECORDING','LIVE_NAMER_NOT_FULLY_DRAINED',
    'LIVE_NAMER_LOG_MISSING','LIVE_NAMER_LOG_SEQUENCE','LIVE_NAMER_SHUTDOWN_FAILED',
    'GUI_SOURCE_INSERTION_UNSAFE','GUI_SOURCE_ROUNDTRIP_MISMATCH','GUI_CI_SOURCE_SYNTAX',
    'GUI_NAMER_SOURCE_CHANGED','GUI_CI_DID_NOT_START_WORKER','GUI_CI_SESSION_INVALID',
    'GUI_CI_WORKER_NOT_OWNED','GUI_CI_WORKER_NOT_READY','GUI_CI_EXITED_DURING_RECORDING',
    'GUI_CI_STOP_BUTTON_FAILED','GUI_CI_EXITED_BEFORE_MP4_DRAIN','GUI_CI_QUIT_TIMEOUT',
    'GUI_CI_QUIT_CLICK_FAILED','GUI_CI_NAMER_NOT_CLOSED',
    'GUI_CI_NAMER_PROCESS_NOT_UNIQUE','GUI_CI_NAMER_PROCESS_EARLY_EXIT',
    'GUI_CI_NAMER_PROCESS_NOT_EXITED','GUI_CI_NAMER_PROCESS_BAD_EXIT',
    'CI_STOP_ALIGNMENT_WORKER_EXITED',
    'CI_EXIT_HEX_ENCODING_FAILED',
    'GUI_STOP_POLICY_WORKER_EXIT','GUI_STOP_POLICY_NO_SIGNAL',
    'GUI_STOP_POLICY_NOT_LAUNCHED','GUI_STOP_POLICY_LAUNCH_COUNT',
    'GUI_STOP_POLICY_MARKER_AT_RETURN','GUI_STOP_POLICY_GST_EXIT',
    'GUI_STOP_POLICY_STOP_DECISION','GUI_STOP_POLICY_RECONNECT',
    'GUI_STOP_POLICY_EOS_MISSING','GUI_STOP_POLICY_RECORD_RETURN',
    'GUI_STOP_POLICY_FRAGMENT_COUNT','GUI_STOP_POLICY_MP4_BYTES',
    'GUI_STOP_POLICY_MARKER_PROOF','GUI_STOP_POLICY_WORKER_READY_LEFT')
  $reason=if($_.Exception.Message -in $known){$_.Exception.Message}else{'BLOCKED'}
  if($phase -ceq 'POST_VERIFICATION_WORKER_STATUS'){
    # Attach the signed worker exit status directly to the one failure line
    # that the workflow is guaranteed to preserve. Numeric PID is NOT logged.
    $reason='GUI_STOP_POLICY_WORKER_EXIT'
  }
  if($phase -ceq 'GUI_STOP_POLICY_CHECK'){
    # Only bounded scalar counters. Never upload original worker transcript,
    # camera credentials, RTSP URLs, file names, or exception messages.
    $recordErrorDetected=[int](([string]$text).Contains('RECORD ERROR:'))
    $gstReturned=[int](([string]$text).Contains('GStreamer returned; exitCode='))
    $eosSuccessful=[int](([string]$text).Contains('Recording stopped by GUI; GStreamer EOS completed.'))
    # Reason token must survive outer workflow's strict A-Z_ log whitelist.
    # Encode small finite categories only, never the user's camera/path/logs.
    $workerClass=if($recordExit -eq 0){'ZERO'}elseif($recordExit -eq 1){'ONE'}elseif($recordExit -eq -1073741510){'CONTROL_C'}else{'OTHER'}
    $gstClass=if($nativeExit -eq 0){'ZERO'}elseif($nativeExit -eq 999){'MISSING'}else{'NONZERO'}
    $eosClass=if($eosSuccessful -eq 1){'YES'}else{'NO'}
    $errorClassToken=if($recordErrorDetected -eq 1){'YES'}else{'NO'}
    $returnedClass=if($returned -eq 1){'YES'}else{'NO'}
    $markerClass=if($markerAtReturn -eq 1){'YES'}else{'NO'}
    $stopClass=if($policyStop -eq 1){'YES'}else{'NO'}
    $readyClass=if($readyRemoved -eq 1){'YES'}else{'NO'}
    $reason=(@('GUI','STOP','WORKER',$workerClass,'GST',$gstClass,'EOS',$eosClass,
      'RECORDERROR',$errorClassToken,'RETURNED',$returnedClass,'MARKER',$markerClass,
      'POLICY',$stopClass,'READYREMOVED',$readyClass) -join '_')
    Write-Output "C545D_WINFORMS_STOP_DIAG,worker_exit=$recordExit,native_gst_exit=$nativeExit,record_error=$recordErrorDetected,gst_returned=$gstReturned,eos_successful=$eosSuccessful,stop_policy=$policyStop,reconnect=$unexpectedReconnect,record_returned=$returned,marker_at_return=$markerAtReturn,mp4_files=$filesCount,stop_proven=$stopExists,ready_removed=$readyRemoved,real_camera=0"
  }
  $errorLine=[int]$_.InvocationInfo.ScriptLineNumber
  $errorClass=[string]$_.Exception.GetType().Name
  if($errorClass -cnotmatch '^[A-Za-z0-9_]{1,80}$'){$errorClass='OTHER'}
  $errorCategory=[string]$_.CategoryInfo.Category
  if($errorCategory -cnotmatch '^[A-Za-z0-9_]{1,80}$'){$errorCategory='OTHER'}
  Write-Output "C545D_GUI_INTEGRATED_ERROR_STAGE,phase=$phase,line=$errorLine,exception_class=$errorClass,category=$errorCategory,worker_exit=$recordExit,media_verified=$mediaVerified,mp4_files=$filesCount,real_camera=0"
  if($phase -ceq 'POST_VERIFICATION_WORKER_STATUS'){
    Write-Output "C545D_GUI_WORKER_RTSP_FAIL,phase=$phase,reason=$reason,worker_exit=$recordExit,media_verified=$mediaVerified,mp4_files=$filesCount,real_camera=0,host_modified=0"
  } else {
    Write-Output "C545D_GUI_WORKER_RTSP_FAIL,phase=$phase,reason=$reason,real_camera=0,host_modified=0"
  }
  throw 'SANITIZED_CI_LOOPBACK_RECORD_TEST_FAILED'
 } finally {
  if($namerOwned){
    if(-not $namerOwned.HasExited){
      # Last-resort cleanup only for the independently checked CI-owned
      # child PowerShell process, never a camera or user's recorder process.
      try {$namerOwned.Kill();[void]$namerOwned.WaitForExit(5000)}catch {}
    }
    $namerOwned.Dispose()
  }
  if($gui){
    if(-not $gui.HasExited){
      # Only CI-owned private GUI process can be stopped after a failed test.
      try {$gui.Kill();[void]$gui.WaitForExit(5000)}catch {}
    }
    $gui.Dispose()
  }
  if($liveNamer){
    if(-not $liveNamer.HasExited){
      # CI-only private watcher child. Never stop or signal a user process.
      try {$liveNamer.Kill();[void]$liveNamer.WaitForExit(5000)}catch {}
    }
    $liveNamer.Dispose()
  }
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
    # FileSystemWatcher may release a handle immediately AFTER .ready is
    # deleted. Only this exact CI-owned child of RUNNER_TEMP may be retried.
    # No new path or ownership is accepted; reject reparse links on every
    # attempt. A permanent lock still fails the job, never a false PASS.
    $ciStageCleanupRetries=0
    $ciStageCleanupError='NONE'
    for($attempt=0;$attempt -lt 16;$attempt++){
      if(-not (Test-Path -LiteralPath $stage)){break}
      $newLinks=@(Get-ChildItem -LiteralPath $stage -Recurse -Force -ErrorAction Stop |
        Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0})
      $rootAttributes=(Get-Item -LiteralPath $stage -Force).Attributes
      if($newLinks.Count -ne 0 -or
         ($rootAttributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){
        throw 'OWNED_STAGE_CLEANUP_REFUSED'
      }
      try {
        Remove-Item -LiteralPath $stage -Force -Recurse -ErrorAction Stop
      } catch {
        $ciStageCleanupError=$_.Exception.GetType().Name
        if($ciStageCleanupError -cnotmatch '^[A-Za-z0-9_]{1,80}$'){$ciStageCleanupError='OTHER'}
      }
      if(-not (Test-Path -LiteralPath $stage)){break}
      $ciStageCleanupRetries++
      Start-Sleep -Milliseconds 250
    }
    $stageRemoved=[int](-not (Test-Path -LiteralPath $stage))
    Write-Output "C545D_GUI_CI_STAGE_CLEANUP,removed=$stageRemoved,retries=$ciStageCleanupRetries,real_camera=0"
    if($stageRemoved -ne 1){throw 'STAGE_CLEANUP_INCOMPLETE'}
  }
}
if($phase -cne 'PASS' -or $mp4Decoded -ne 1 -or $eosObserved -ne 1 -or $signalSent -ne 1){
  throw 'GUI_CTRL_C_EOS_NOT_QUALIFIED'
}
Write-Output "C545D_GUI_ACCELERATED_SPLIT_CI_PASS,original_worker=1,ci_modified_split_only=1,synthetic_rtsp=1,fragments=$filesCount,each_mp4_decoded=1,gui_ctrlc_eos=1,owned_rollback=1,real_hourly_split_tested=0,real_camera=0,install_approved=0"
