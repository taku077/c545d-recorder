#Requires -Version 5.1
<#
CI-ONLY micro-test for the exact, unchanged RecordGUIWorker.ps1 console
handler. The stage-only Record.ps1 is an inert marker consumer; no GStreamer,
RTSP, camera, original settings or installed DLL is loaded or modified.
This does not validate real EOS/MP4, which have separate synthetic RTSP gates.
#>
$ErrorActionPreference='Stop'
$phase='GUARD';$result='BLOCKED';$passed=0;$total=3
$root=$null;$stage=$null;$stageOwned=$false;$activeWorker=$null
$oldLocal=[Environment]::GetEnvironmentVariable('LOCALAPPDATA','Process')
try {
  if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
     -not $env:RUNNER_TEMP){throw 'NOT_ISOLATED_WINDOWS_CI'}
  $root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
  $source=Join-Path $root 'RecordGUIWorker.ps1'
  $sourceHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
  $temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
  $tempItem=Get-Item -LiteralPath $temp -Force -ErrorAction Stop
  if(-not $tempItem.PSIsContainer -or
     ($tempItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'BAD_RUNNER_TEMP'}
  $stage=Join-Path $temp ('c545d-ci-worker-ctrlc-'+[guid]::NewGuid().ToString('N'))
  [void](New-Item -Path $stage -ItemType Directory -ErrorAction Stop)
  [IO.File]::WriteAllText((Join-Path $stage '.c545d-test-owned'),'CI_CTRL_C_WORKER_ONLY')
  $stageOwned=$true
  Copy-Item -LiteralPath $source -Destination (Join-Path $stage 'RecordGUIWorker.ps1')
  if((Get-FileHash -LiteralPath (Join-Path $stage 'RecordGUIWorker.ps1') -Algorithm SHA256).Hash -cne $sourceHash){
    throw 'WORKER_COPY_CHANGED'
  }
  $stub=@'
param([Parameter(Mandatory=$true)][string]$StopFile)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
   [IO.File]::ReadAllText((Join-Path $root '.c545d-test-owned')) -cne 'CI_CTRL_C_WORKER_ONLY'){
  throw 'CI_STUB_GUARD'
}
$id=[IO.Path]::GetFileNameWithoutExtension($StopFile)
[IO.File]::WriteAllText((Join-Path $root ('ci-stub-running-'+$id)),'READY')
$observed=$false
for($i=0;$i -lt 220;$i++){
  if(Test-Path -LiteralPath $StopFile -PathType Leaf){$observed=$true;break}
  Start-Sleep -Milliseconds 50
}
if(-not $observed){throw 'CI_STUB_STOP_TIMEOUT'}
# Simulate a nontrivial EOS delay while the unchanged worker's
# console handler must swallow precisely one Ctrl+C without exiting.
Start-Sleep -Milliseconds 4000
[IO.File]::WriteAllText((Join-Path $root ('ci-stub-finished-'+$id)),'EOS_SIMULATED_ONLY')
'@
  [IO.File]::WriteAllText((Join-Path $stage 'Record.ps1'),$stub,(New-Object Text.UTF8Encoding($false)))
  # The helper verifies exact Windows parent, executable and owned CLI,
  # plus a private console containing no other unrelated process.
  $helper=@'
param([Parameter(Mandatory=$true)][string]$Stage,
      [Parameter(Mandatory=$true)][int]$WorkerId,
      [Parameter(Mandatory=$true)][int]$ExpectedParent)
$ErrorActionPreference='Stop'
$attached=$false;$protected=$false;$sent=$false
try {
  if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
     [IO.File]::ReadAllText((Join-Path $Stage '.c545d-test-owned')) -cne 'CI_CTRL_C_WORKER_ONLY'){
    throw 'CI_HELPER_GUARD'
  }
  $worker=Get-CimInstance Win32_Process -Filter ("ProcessId = "+$WorkerId) -ErrorAction Stop
  $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $owned=Join-Path $Stage 'RecordGUIWorker.ps1'
  if(-not $worker -or [int]$worker.ParentProcessId -ne $ExpectedParent -or
     -not [string]::Equals([IO.Path]::GetFullPath([string]$worker.ExecutablePath),
       [IO.Path]::GetFullPath($ps),[StringComparison]::OrdinalIgnoreCase) -or
     ([string]$worker.CommandLine).IndexOf($owned,[StringComparison]::OrdinalIgnoreCase) -lt 0){
    throw 'CI_HELPER_WORKER_NOT_OWNED'
  }
  Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class C545DCIConsoleOnly {
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool FreeConsole();
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool AttachConsole(uint id);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool SetConsoleCtrlHandler(IntPtr handler,bool add);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern uint GetConsoleProcessList([Out] uint[] ids,uint size);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool GenerateConsoleCtrlEvent(uint code,uint group);
}
"@
  [void][C545DCIConsoleOnly]::FreeConsole()
  $attached=[C545DCIConsoleOnly]::AttachConsole([uint32]$WorkerId)
  if(-not $attached){throw 'CI_HELPER_CONSOLE_ATTACH_FAILED'}
  $ids=New-Object 'uint32[]' 12
  $count=[C545DCIConsoleOnly]::GetConsoleProcessList($ids,[uint32]$ids.Length)
  $self=[uint32]$PID
  if($count -ne 2 -or @($ids[0],$ids[1]) -notcontains ([uint32]$WorkerId) -or
     @($ids[0],$ids[1]) -notcontains $self){
    throw 'CI_HELPER_CONSOLE_NOT_EXCLUSIVE'
  }
  $protected=[C545DCIConsoleOnly]::SetConsoleCtrlHandler([IntPtr]::Zero,$true)
  if(-not $protected){throw 'CI_HELPER_PROTECT_FAILED'}
  $sent=[C545DCIConsoleOnly]::GenerateConsoleCtrlEvent(0,0)
  if(-not $sent){throw 'CI_HELPER_SIGNAL_FAILED'}
  Write-Output 'C545D_CI_PRIVATE_CTRL_C_SIGNAL,sent=1,owned_console=1,rtsp=0'
} finally {
  if($attached){[void][C545DCIConsoleOnly]::FreeConsole()}
  if($protected){[void][C545DCIConsoleOnly]::SetConsoleCtrlHandler([IntPtr]::Zero,$false)}
}
if(-not $sent){exit 3}
'@
  $helperPath=Join-Path $stage 'ci-private-console-signal.ps1'
  [IO.File]::WriteAllText($helperPath,$helper,(New-Object Text.UTF8Encoding($false)))
  $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $env:LOCALAPPDATA=Join-Path $stage 'private-localappdata'
  [void](New-Item -Path $env:LOCALAPPDATA -ItemType Directory -ErrorAction Stop)
  $phase='TRIALS'
  $trial=0
  foreach($delay in @(0,150,500)){
    $trial++
    $session=[guid]::NewGuid().ToString('N')
    $control=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Control'
    $ready=Join-Path $control ('session_'+$session+'.ready')
    $stop=Join-Path $control ('session_'+$session+'.stop')
    $stubId='session_'+$session
    $stubStarted=Join-Path $stage ('ci-stub-running-'+$stubId)
    $stubFinished=Join-Path $stage ('ci-stub-finished-'+$stubId)
    $workerArgs=@('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
      '-File',('"'+(Join-Path $stage 'RecordGUIWorker.ps1')+'"'),'-SessionId',$session)
    $activeWorker=Start-Process -FilePath $ps -ArgumentList $workerArgs -WorkingDirectory $stage -WindowStyle Hidden -PassThru
    $readyOk=$false
    for($wait=0;$wait -lt 160;$wait++){
      if($activeWorker.HasExited){break}
      if((Test-Path -LiteralPath $ready -PathType Leaf) -and
         (Test-Path -LiteralPath $stubStarted -PathType Leaf)){
        $readyOk=([IO.File]::ReadAllText($ready).Trim() -ceq [string]$activeWorker.Id)
        if($readyOk){break}
      }
      Start-Sleep -Milliseconds 50
    }
    if(-not $readyOk){throw 'WORKER_READY_NOT_OBSERVED'}
    [IO.File]::WriteAllText($stop,'CI_PRIVATE_STOP_ONLY')
    if($delay -gt 0){Start-Sleep -Milliseconds $delay}
    $sigLines=@(& $ps -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $helperPath -Stage $stage -WorkerId $activeWorker.Id -ExpectedParent $PID 2>$null)
    if($LASTEXITCODE -ne 0 -or $sigLines.Count -ne 1 -or
       $sigLines[0] -cne 'C545D_CI_PRIVATE_CTRL_C_SIGNAL,sent=1,owned_console=1,rtsp=0'){
      throw 'PRIVATE_CONSOLE_SIGNAL_NOT_SENT'
    }
    if(-not $activeWorker.WaitForExit(20000)){throw 'WORKER_NOT_STOPPED'}
    $actual=[int]$activeWorker.ExitCode
    if($actual -ne 0){throw 'WORKER_EXIT_NONZERO'}
    if(-not (Test-Path -LiteralPath $stubFinished -PathType Leaf) -or
       (Test-Path -LiteralPath $ready -PathType Leaf)){throw 'WORKER_STOP_NOT_FINALIZED'}
    $logDir=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Logs'
    $logs=@(Get-ChildItem -LiteralPath $logDir -Filter ('Recording_*_'+$activeWorker.Id+'.txt') -File -ErrorAction Stop)
    if($logs.Count -ne 1){throw 'WORKER_TRANSCRIPT_NOT_UNIQUE'}
    $transcript=[IO.File]::ReadAllText($logs[0].FullName)
    if(-not $transcript.Contains('Record.ps1 returned; stopMarker=True; pendingCtrlCEvents=1') -or
       $transcript.Contains('RECORD ERROR:')){throw 'WORKER_HANDLER_COUNT_OR_SCRIPT_BAD'}
    $passed++
    $activeWorker.Dispose()
    $activeWorker=$null
  }
  if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -cne $sourceHash){throw 'PRODUCTION_SOURCE_CHANGED'}
  $result='PASS'
} catch {
  $code=[string]$_.Exception.Message
  $allow=@('NOT_ISOLATED_WINDOWS_CI','BAD_RUNNER_TEMP','WORKER_COPY_CHANGED',
    'WORKER_READY_NOT_OBSERVED','PRIVATE_CONSOLE_SIGNAL_NOT_SENT',
    'WORKER_NOT_STOPPED','WORKER_EXIT_NONZERO','WORKER_STOP_NOT_FINALIZED',
    'WORKER_TRANSCRIPT_NOT_UNIQUE','WORKER_HANDLER_COUNT_OR_SCRIPT_BAD',
    'PRODUCTION_SOURCE_CHANGED')
  $result=if($code -in $allow){$code}else{'BLOCKED'}
} finally {
  if($activeWorker){
    if(-not $activeWorker.HasExited){
      # Only this exact stage-launched CI worker; no user recorder contact.
      try {$activeWorker.Kill();[void]$activeWorker.WaitForExit(4000)}catch {}
    }
    $activeWorker.Dispose()
  }
  [Environment]::SetEnvironmentVariable('LOCALAPPDATA',$oldLocal,'Process')
  if($stageOwned -and (Test-Path -LiteralPath $stage -PathType Container)){
    try{
      $dir=Get-Item -LiteralPath $stage -Force
      $links=@(Get-ChildItem -LiteralPath $stage -Force -Recurse -ErrorAction Stop |
         Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0})
      $parent=[IO.Path]::GetDirectoryName($stage).TrimEnd('\')
      if(($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
         $links.Count -ne 0 -or
         -not [string]::Equals($parent,$temp,[StringComparison]::OrdinalIgnoreCase) -or
         [IO.Path]::GetFileName($stage) -notmatch '^c545d-ci-worker-ctrlc-[a-f0-9]{32}$' -or
         [IO.File]::ReadAllText((Join-Path $stage '.c545d-test-owned')) -cne 'CI_CTRL_C_WORKER_ONLY'){
         throw 'CLEANUP_REFUSED'
      }
      $removed=$false
      for($k=0;$k -lt 15;$k++){
        try {Remove-Item -LiteralPath $stage -Force -Recurse -ErrorAction Stop;$removed=$true;break}
        catch {Start-Sleep -Milliseconds 250}
      }
      if(-not $removed){$result='CI_CLEANUP_LOCKED'}
    }catch{$result='CI_CLEANUP_REFUSED'}
  }
}
Write-Output "C545D_ORIGINAL_WORKER_CTRL_C_CI,trials=$total,passed=$passed,original_worker=1,private_stub=1,one_ctrl_c_per_trial=1,real_rtsp=0,real_camera=0,host_modified=0,reason=$result"
if($result -ceq 'PASS' -and $passed -eq $total){exit 0}
exit 3
