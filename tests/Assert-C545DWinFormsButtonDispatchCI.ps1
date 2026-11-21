#Requires -Version 5.1
<#
CI ONLY. Invoke the actual WinForms START, STOP and QUIT button Click handlers
on a private one-insertion mirror of C545D_App.ps1. A harmless stub replaces
RecordGUIWorker ONLY IN THIS disposable CI stage; it never touches RTSP.
This checks real GUI wiring and the safe early-stop marker path, NOT GStreamer
EOS, actual recording, human-driven UI input, or Win10 camera behavior.
#>
$ErrorActionPreference='Stop'
$phase='PRECHECK';$result='BLOCKED';$start=0;$stop=0;$quit=0
$namerReady=0;$workerStub=0;$safeMarker=0;$sourcesIntact=0
$stage=$null;$gui=$null;$stageOwned=$false;$oldEnv=$null
$oldPSModulePath=$null
try {
  if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
     -not $env:RUNNER_TEMP){throw 'CI_ONLY'}
  $root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
  $temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
  $tempInfo=Get-Item -LiteralPath $temp -Force
  if(-not $tempInfo.PSIsContainer -or
     ($tempInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){
    throw 'UNSAFE_TEMP'
  }
  $sources=@('C545D_App.ps1','CommonSettings.ps1',
             'SegmentNamer.ps1','SegmentNamerWorker.ps1')
  $original=@{}
  $sha=@{}
  foreach($name in $sources){
    $p=Join-Path $root $name
    $original[$name]=[IO.File]::ReadAllText($p)
    $sha[$name]=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash
  }
  $stage=Join-Path $temp ('c545d-ci-gui-event-'+[guid]::NewGuid().ToString('N'))
  [void](New-Item -ItemType Directory -Path $stage -ErrorAction Stop)
  $owner=Join-Path $stage '.c545d-ci-gui-owned'
  [IO.File]::WriteAllText($owner,'C545D_GUI_CI_PRIVATE_ONLY')
  $stageOwned=$true
  # Original GUI and namer scripts include Japanese messages and UTF-8 BOM.
  # Windows PowerShell 5.1 treats UTF-8 WITHOUT BOM as the system ANSI code
  # page, so the clone must retain BOM even though ReadAllText strips it.
  foreach($name in $sources){
    [IO.File]::WriteAllText((Join-Path $stage $name),$original[$name],
                           (New-Object Text.UTF8Encoding($true)))
  }
  $output=Join-Path $stage 'synthetic-output'
  $privateLocal=Join-Path $stage 'ci-localappdata'
  [void](New-Item -Path $output -ItemType Directory)
  [void](New-Item -Path $privateLocal -ItemType Directory)
  $marker=Join-Path $stage 'ci-event-state.txt'
  # The only recorder-like child is a synthetic marker consumer. It does not
  # create the .ready marker, so real Request-Stop MUST take its safe early
  # stop path without AttachConsole or GenerateConsoleCtrlEvent.
  $stub=@'
param([Parameter(Mandatory=$true)][string]$SessionId)
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows'){exit 3}
$root=$PSScriptRoot
if([IO.File]::ReadAllText((Join-Path $root '.c545d-ci-gui-owned')) -cne 'C545D_GUI_CI_PRIVATE_ONLY'){exit 3}
$control=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Control'
$stop=Join-Path $control ('session_'+$SessionId+'.stop')
[IO.File]::WriteAllText((Join-Path $root 'ci-stub-started'),'1')
for($i=0;$i -lt 250;$i++){
  if(Test-Path -LiteralPath $stop -PathType Leaf){
    [IO.File]::WriteAllText((Join-Path $root 'ci-stub-saw-safe-stop'),'1')
    exit 0
  }
  Start-Sleep -Milliseconds 100
}
exit 3
'@
  [IO.File]::WriteAllText((Join-Path $stage 'RecordGUIWorker.ps1'),$stub,
                         (New-Object Text.UTF8Encoding($false)))
  $phase='SOURCE_INJECTION'
  $anchor='[void][System.Windows.Forms.Application]::Run($form)'
  $source=$original['C545D_App.ps1']
  if([regex]::Matches($source,[regex]::Escape($anchor)).Count -ne 1){
    throw 'GUI_ANCHOR_NOT_UNIQUE'
  }
  $ciHook=@'
# CI injected controlled Form.Timer, attached to the actual form's GUI thread.
# Real original btnStart/btnStop/btnQuit handlers are not replaced.
$script:ciStageStart=Get-Date
$script:ciClickPhase=0
$script:ciStartOk=0
$script:ciStopOk=0
$script:ciNamerReady=0
$ciState=Join-Path $PSScriptRoot 'ci-event-state.txt'
$ciClickTimer=New-Object System.Windows.Forms.Timer
$ciClickTimer.Interval=200
$ciClickTimer.Add_Tick({
  try {
    if(((Get-Date)-$script:ciStageStart).TotalSeconds -gt 23){
      throw 'GUI_EVENT_TIMEOUT'
    }
    switch($script:ciClickPhase) {
      0 {
        if(-not (Test-Path -LiteralPath $txtOutput.Text -PathType Container)){
          throw 'GUI_OUTPUT_NOT_PRIVATE'
        }
        $btnStart.PerformClick()
        if(-not (Is-Recording)){throw 'START_CLICK_NO_WORKER'}
        if(-not $script:namerReadyFile -or
           -not (Test-Path -LiteralPath $script:namerReadyFile -PathType Leaf)){
          throw 'NAMER_NOT_READY_BEFORE_RECORD'
        }
        $script:ciNamerReady=1
        $script:ciStartOk=1
        $script:ciClickPhase=1
      }
      1 {
        if(-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'ci-stub-started'))){break}
        $btnStop.PerformClick()
        if(-not $script:stopRequested -or
           -not (Test-Path -LiteralPath $script:stopFile -PathType Leaf)){
          throw 'STOP_CLICK_MARKER_MISSING'
        }
        $script:ciStopOk=1
        $script:ciClickPhase=2
      }
      2 {
        if(-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'ci-stub-saw-safe-stop'))){break}
        if(Is-Recording){break}
        [IO.File]::WriteAllText($ciState,
          "C545D_WINFORMS_BUTTON_CI_PASS,start=$($script:ciStartOk),stop=$($script:ciStopOk),namer_ready=$($script:ciNamerReady),worker_stub_stop=1,exit_requested=1,real_rtsp=0,real_camera=0,install_approved=0")
        $btnQuit.PerformClick()
        $script:ciClickPhase=3
      }
    }
  } catch {
    $errorCode=[string]$_.Exception.Message
    $allowed=@('GUI_EVENT_TIMEOUT','GUI_OUTPUT_NOT_PRIVATE','START_CLICK_NO_WORKER',
      'NAMER_NOT_READY_BEFORE_RECORD','STOP_CLICK_MARKER_MISSING')
    if($errorCode -notin $allowed){$errorCode='BLOCKED'}
    [IO.File]::WriteAllText($ciState,'C545D_WINFORMS_BUTTON_CI_FAIL,reason='+$errorCode)
    $script:allowExit=$true
    $form.Close()
  }
})
$ciClickTimer.Start()
'@
  $patched=$source.Replace($anchor,$ciHook+[Environment]::NewLine+$anchor)
  if($patched.Replace($ciHook+[Environment]::NewLine+$anchor,$anchor) -cne $source){
    throw 'GUI_ROUNDTRIP_DIFF'
  }
  $t=$null;$err=$null
  [void][Management.Automation.Language.Parser]::ParseInput($patched,[ref]$t,[ref]$err)
  if($err.Count -gt 0){throw 'GUI_PATCH_SYNTAX'}
  [IO.File]::WriteAllText((Join-Path $stage 'C545D_App.ps1'),$patched,
                          (New-Object Text.UTF8Encoding($true)))
  $phase='BOOTSTRAP'
  $bootstrap=@'
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows'){exit 3}
$root=$PSScriptRoot
if([IO.File]::ReadAllText((Join-Path $root '.c545d-ci-gui-owned')) -cne 'C545D_GUI_CI_PRIVATE_ONLY'){exit 3}
$env:LOCALAPPDATA=Join-Path $root 'ci-localappdata'
$settings=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer'
[void](New-Item -ItemType Directory -Force -Path $settings)
$cfg=@{version=2;camera_ip='127.0.0.1';camera_user='CI_FAKE_ONLY';output_folder=(Join-Path $root 'synthetic-output')}
[IO.File]::WriteAllText((Join-Path $settings 'settings.json'),($cfg|ConvertTo-Json),
                         (New-Object Text.UTF8Encoding($false)))
$fake=ConvertTo-SecureString 'CI_DUMMY_NEVER_REAL' -AsPlainText -Force
$encrypted=ConvertFrom-SecureString $fake
[IO.File]::WriteAllText((Join-Path $settings 'camera_password.dpapi'),$encrypted)
$global:ProgressPreference='SilentlyContinue'
[IO.File]::WriteAllText((Join-Path $root 'ci-gui-boot-phase'),'PREPARED')
try {
  [IO.File]::WriteAllText((Join-Path $root 'ci-gui-boot-phase'),'GUI_STARTED')
  & (Join-Path $root 'C545D_App.ps1')
  [IO.File]::WriteAllText((Join-Path $root 'ci-gui-boot-phase'),'GUI_RETURNED')
} catch {
  $id=[string]$_.FullyQualifiedErrorId
  if($id -cnotmatch '^[A-Za-z0-9_]{1,80}$'){$id='OTHER'}
  [IO.File]::WriteAllText((Join-Path $root 'ci-child-error-id'),$id)
  [IO.File]::WriteAllText((Join-Path $root 'ci-gui-boot-phase'),'GUI_EXCEPTION')
  exit 3
}
'@
  [IO.File]::WriteAllText((Join-Path $stage 'ci-gui-bootstrap.ps1'),$bootstrap,
                          (New-Object Text.UTF8Encoding($false)))
  $guiExe=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $stdOut=Join-Path $stage 'ci-gui-stdout.txt'
  $stdErr=Join-Path $stage 'ci-gui-stderr.txt'
  $phase='GUI_CHILD'
  $previous=[Environment]::GetEnvironmentVariable('PSModulePath','Process')
  try {
    [Environment]::SetEnvironmentVariable('PSModulePath',$null,'Process')
    $gui=Start-Process -FilePath $guiExe -ArgumentList @(
      '-NoLogo','-NoProfile','-STA','-ExecutionPolicy','Bypass',
      '-File',('"'+(Join-Path $stage 'ci-gui-bootstrap.ps1')+'"')
    ) -WorkingDirectory $stage -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdOut -RedirectStandardError $stdErr
  } finally {
    [Environment]::SetEnvironmentVariable('PSModulePath',$previous,'Process')
  }
  if(-not $gui.WaitForExit(32000)){throw 'GUI_WAIT_TIMEOUT'}
  $phase='VERIFY'
  if(-not (Test-Path -LiteralPath $marker -PathType Leaf)){
    $bootPhase='NOT_STARTED'
    $bootMarker=Join-Path $stage 'ci-gui-boot-phase'
    if(Test-Path -LiteralPath $bootMarker -PathType Leaf){
      $bootPhase=[IO.File]::ReadAllText($bootMarker).Trim()
      if($bootPhase -notin @('PREPARED','GUI_STARTED','GUI_RETURNED','GUI_EXCEPTION')){$bootPhase='UNRECOGNIZED'}
    }
    $errorId='NONE'
    $errorMarker=Join-Path $stage 'ci-child-error-id'
    if(Test-Path -LiteralPath $errorMarker -PathType Leaf){
      $errorId=[IO.File]::ReadAllText($errorMarker).Trim()
      if($errorId -cnotmatch '^[A-Za-z0-9_]{1,80}$'){$errorId='OTHER'}
    }
    Write-Output "C545D_WINFORMS_CHILD_DIAG,boot=$bootPhase,error_id=$errorId,gui_exit=$($gui.ExitCode),real_rtsp=0"
  }
  if(-not (Test-Path -LiteralPath $marker -PathType Leaf)){throw 'GUI_NO_RESULT'}
  $line=[IO.File]::ReadAllText($marker).Trim()
  $expected='C545D_WINFORMS_BUTTON_CI_PASS,start=1,stop=1,namer_ready=1,worker_stub_stop=1,exit_requested=1,real_rtsp=0,real_camera=0,install_approved=0'
  if($line -cne $expected){throw 'GUI_EVENT_CHECK_FAILED'}
  $start=1;$stop=1;$quit=1;$namerReady=1;$workerStub=1;$safeMarker=1
  # Only source snapshots from the real repository are immutable.
  $sourcesIntact=1
  foreach($name in $sources){
    if((Get-FileHash -LiteralPath (Join-Path $root $name) -Algorithm SHA256).Hash -cne $sha[$name]){
      $sourcesIntact=0;throw 'ORIGINAL_SOURCE_CHANGED'
    }
  }
  $result='PASS'
} catch {
  $allowed=@('CI_ONLY','UNSAFE_TEMP','GUI_ANCHOR_NOT_UNIQUE','GUI_ROUNDTRIP_DIFF',
    'GUI_PATCH_SYNTAX','GUI_WAIT_TIMEOUT','GUI_NO_RESULT',
    'GUI_EVENT_CHECK_FAILED','ORIGINAL_SOURCE_CHANGED')
  if([string]$_.Exception.Message -in $allowed){$result=[string]$_.Exception.Message}
  else {$result='BLOCKED'}
} finally {
  if($gui){
    if(-not $gui.HasExited){
      # A failure can kill ONLY this CI-owned GUI child, never a user process.
      try {$gui.Kill();[void]$gui.WaitForExit(4000)}catch {}
    }
    $gui.Dispose()
  }
  if($stageOwned -and $stage -and (Test-Path -LiteralPath $stage -PathType Container)){
    $dir=Get-Item -LiteralPath $stage -Force
    $linked=@(Get-ChildItem -LiteralPath $stage -Recurse -Force -ErrorAction Stop |
      Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0})
    if(($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
       $linked.Count -ne 0 -or
       -not [string]::Equals(([IO.Path]::GetDirectoryName($stage)).TrimEnd('\'),
                            $temp,[StringComparison]::OrdinalIgnoreCase) -or
       [IO.Path]::GetFileName($stage) -notmatch '^c545d-ci-gui-event-[a-f0-9]{32}$' -or
       [IO.File]::ReadAllText((Join-Path $stage '.c545d-ci-gui-owned')) -cne
           'C545D_GUI_CI_PRIVATE_ONLY'){
      throw 'GUI_CI_CLEANUP_REFUSED'
    }
    Remove-Item -LiteralPath $stage -Force -Recurse -ErrorAction Stop
  }
}
Write-Output "C545D_WINFORMS_BUTTON_DISPATCH_STAGE,start=$start,stop=$stop,quit=$quit,namer_ready=$namerReady,stub_safe_stop=$safeMarker,source_unchanged=$sourcesIntact,real_rtsp=0,real_camera=0,install_approved=0,reason=$result"
if($result -ceq 'PASS'){exit 0}
exit 3
