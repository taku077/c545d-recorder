#Requires -Version 5.1
<#
 CI-only smoke: test the existing GUI worker Ctrl+C handler and GUI protocol
 against a disposable synthetic worker, with NO GStreamer, user camera,
 passwords, video, production process or host settings.
#>
$ErrorActionPreference='Stop'
$stage=$null;$worker=$null;$owned=$false;$pass=$false
$phase='PRECONDITION'
try {
  if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
     -not $env:RUNNER_TEMP){throw 'NOT_DISPOSABLE_WINDOWS_CI'}
  $root=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
  $rootItem=Get-Item -LiteralPath $root -Force
  if(-not $rootItem.PSIsContainer -or
     ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){
    throw 'UNSAFE_RUNNER_TEMP'
  }
  $source=(Resolve-Path -LiteralPath RecordGUIWorker.ps1).Path
  $gui=(Resolve-Path -LiteralPath C545D_App.ps1).Path
  $sourceHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
  $guiHash=(Get-FileHash -LiteralPath $gui -Algorithm SHA256).Hash
  $workerText=[IO.File]::ReadAllText($source)
  $codePattern="(?s)Add-Type -TypeDefinition @'\r?\n.*?\r?\n'@"
  $matches=[regex]::Matches($workerText,$codePattern)
  if($matches.Count -ne 1 -or
     -not $matches[0].Value.Contains('C545DWorkerStopSignal') -or
     -not $matches[0].Value.Contains('SetConsoleCtrlHandler')){
    throw 'WORKER_HANDLER_NOT_EXACT'
  }
  $app=[IO.File]::ReadAllText($gui)
  $a=$app.IndexOf('function Request-Stop {',[StringComparison]::Ordinal)
  $b=$app.IndexOf('function Request-EmergencyStop {',[StringComparison]::Ordinal)
  if($a -lt 0 -or $b -le $a){throw 'GUI_STOP_ROUTINE_MISSING'}
  $stopRoutine=$app.Substring($a,$b-$a)
  $first=$stopRoutine.IndexOf('WriteAllText($script:stopFile',[StringComparison]::Ordinal)
  $second=$stopRoutine.IndexOf('AttachConsole([uint32]$script:worker.Id)',[StringComparison]::Ordinal)
  $third=$stopRoutine.IndexOf('GenerateConsoleCtrlEvent(0,0)',[StringComparison]::Ordinal)
  if($first -lt 0 -or $second -le $first -or $third -le $second){
    throw 'GUI_STOP_ORDER_CHANGED'
  }
  $stage=Join-Path $root ('c545d-ci-console-stop-'+[guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $stage | Out-Null
  [IO.File]::WriteAllText((Join-Path $stage '.c545d-ci-owned'),'C545D_CONSOLE_STOP_CI_ONLY')
  $owned=$true
  $ready=Join-Path $stage 'worker.ready'
  $stop=Join-Path $stage 'worker.stop'
  $done=Join-Path $stage 'worker.done'
  $workerScript=Join-Path $stage 'ci-worker.ps1'
  $signalScript=Join-Path $stage 'ci-signal.ps1'
  # Never rewrite the C# stop handler: extract the whole original here-string
  # from RecordGUIWorker.ps1 and exercise that exact installation code.
  $workerBody=@(
    'param([string]$Ready,[string]$Done)',
    '$ErrorActionPreference="Stop"',
    $matches[0].Value,
    'if(-not [C545DWorkerStopSignal]::Install()){exit 3}',
    '[IO.File]::WriteAllText($Ready,"WORKER_HANDLER_READY")',
    '$deadline=[Diagnostics.Stopwatch]::StartNew()',
    'while($deadline.Elapsed.TotalSeconds -lt 30){',
    '  if([C545DWorkerStopSignal]::StopRequested){',
    '    [IO.File]::WriteAllText($Done,"CTRL_C_EVENT_HANDLED")',
    '    exit 0',
    '  }',
    '  Start-Sleep -Milliseconds 100',
    '}',
    'exit 3'
  )
  [IO.File]::WriteAllText($workerScript,($workerBody -join [Environment]::NewLine),
    [Text.UTF8Encoding]::new($false))
  $signalBody=@(
    'param([int]$TargetPid,[string]$StopPath)',
    '$ErrorActionPreference="Stop"',
    "Add-Type -TypeDefinition @'",
    'using System;',
    'using System.Runtime.InteropServices;',
    'public static class C545DCiSignal {',
    ' [DllImport("kernel32.dll",SetLastError=true)] public static extern bool FreeConsole();',
    ' [DllImport("kernel32.dll",SetLastError=true)] public static extern bool AttachConsole(uint pid);',
    ' [DllImport("kernel32.dll",SetLastError=true)] public static extern bool GenerateConsoleCtrlEvent(uint evt,uint group);',
    ' [DllImport("kernel32.dll",SetLastError=true)] public static extern bool SetConsoleCtrlHandler(IntPtr handler,bool add);',
    ' [DllImport("kernel32.dll",SetLastError=true)] public static extern uint GetConsoleProcessList([Out] uint[] processes,uint size);',
    '}',
    "'@",
    '[IO.File]::WriteAllText($StopPath,"CI_STOP_BEFORE_SIGNAL")',
    '[void][C545DCiSignal]::FreeConsole()',
    'if(-not [C545DCiSignal]::AttachConsole([uint32]$TargetPid)){exit 4}',
    'try {',
    ' $ids=New-Object uint32[] 16',
    ' $count=[C545DCiSignal]::GetConsoleProcessList($ids,[uint32]$ids.Length)',
    ' if($count -lt 1 -or $count -gt 2){exit 7}',
    ' $seenWorker=$false',
    ' for($i=0;$i -lt $count;$i++){',
    '   if($ids[$i] -eq [uint32]$TargetPid){$seenWorker=$true}',
    '   elseif($ids[$i] -ne [uint32]$PID){exit 7}',
    ' }',
    ' if(-not $seenWorker){exit 7}',
    ' if(-not [C545DCiSignal]::SetConsoleCtrlHandler([IntPtr]::Zero,$true)){exit 5}',
    ' if(-not [C545DCiSignal]::GenerateConsoleCtrlEvent(0,0)){exit 6}',
    ' Start-Sleep -Milliseconds 500',
    '} finally {',
    ' [void][C545DCiSignal]::FreeConsole()',
    '}',
    'exit 0'
  )
  [IO.File]::WriteAllText($signalScript,($signalBody -join [Environment]::NewLine),
    [Text.UTF8Encoding]::new($false))
  $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $phase='WORKER_START'
  $workerArgs=@('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
       '-File',('"'+$workerScript+'"'),'-Ready',('"'+$ready+'"'),'-Done',('"'+$done+'"'))
  $worker=Start-Process -FilePath $ps -ArgumentList $workerArgs -WindowStyle Hidden -WorkingDirectory $root -PassThru
  $seen=$false
  for($i=0;$i -lt 120;$i++){
    Start-Sleep -Milliseconds 100
    if($worker.HasExited){break}
    if(Test-Path -LiteralPath $ready){
      $seen=([IO.File]::ReadAllText($ready) -ceq 'WORKER_HANDLER_READY')
      if($seen){break}
    }
  }
  if(-not $seen){throw 'WORKER_CONSOLE_NOT_READY'}
  if(Test-Path -LiteralPath $done){throw 'UNEXPECTED_PRE_SIGNAL_COMPLETION'}
  $phase='CTRL_C_EVENT'
  $rows=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $signalScript -TargetPid $worker.Id -StopPath $stop 2>$null)
  if($LASTEXITCODE -ne 0){throw 'WORKER_CONSOLE_SIGNAL_FAILED'}
  if(-not $worker.WaitForExit(10000)){throw 'WORKER_DID_NOT_HANDLE_CTRL_C'}
  if(-not (Test-Path -LiteralPath $stop) -or
     [IO.File]::ReadAllText($stop) -cne 'CI_STOP_BEFORE_SIGNAL' -or
     -not (Test-Path -LiteralPath $done) -or
     [IO.File]::ReadAllText($done) -cne 'CTRL_C_EVENT_HANDLED' -or
     $worker.ExitCode -ne 0){throw 'CTRL_C_HANDLING_NOT_PROVEN'}
  $phase='CHECK_BYTES'
  if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -cne $sourceHash -or
     (Get-FileHash -LiteralPath $gui -Algorithm SHA256).Hash -cne $guiHash){
    throw 'GUI_WORKER_SOURCE_CHANGED'
  }
  $pass=$true
} catch {
  $known=@('NOT_DISPOSABLE_WINDOWS_CI','UNSAFE_RUNNER_TEMP',
      'WORKER_HANDLER_NOT_EXACT','GUI_STOP_ROUTINE_MISSING',
      'GUI_STOP_ORDER_CHANGED','WORKER_CONSOLE_NOT_READY',
      'UNEXPECTED_PRE_SIGNAL_COMPLETION','WORKER_CONSOLE_SIGNAL_FAILED',
      'WORKER_DID_NOT_HANDLE_CTRL_C','CTRL_C_HANDLING_NOT_PROVEN',
      'GUI_WORKER_SOURCE_CHANGED')
  $reason=if($_.Exception.Message -in $known){$_.Exception.Message}else{'BLOCKED'}
  Write-Output "C545D_CONSOLE_STOP_BASELINE_FAIL,phase=$phase,reason=$reason,real_camera=0,host_modified=0"
  throw 'SANITIZED_C545D_CONSOLE_CI_FAILED'
} finally {
  if($worker){
    if(-not $worker.HasExited){try{$worker.Kill();[void]$worker.WaitForExit(4000)}catch{}}
    $worker.Dispose()
  }
  if($owned -and $stage -and (Test-Path -LiteralPath $stage)){
    $dir=Get-Item -LiteralPath $stage -Force
    $links=@(Get-ChildItem -LiteralPath $stage -Recurse -Force |
       Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0})
    if(-not $dir.PSIsContainer -or
       ($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
       $links.Count -ne 0 -or
       -not [string]::Equals([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($stage)).TrimEnd('\'),
                            $root,[StringComparison]::OrdinalIgnoreCase) -or
       [IO.Path]::GetFileName($stage) -notmatch '^c545d-ci-console-stop-[a-f0-9]{32}$' -or
       [IO.File]::ReadAllText((Join-Path $stage '.c545d-ci-owned')) -cne 'C545D_CONSOLE_STOP_CI_ONLY'){
      throw 'OWNED_CONSOLE_CI_CLEANUP_REFUSED'
    }
    Remove-Item -LiteralPath $stage -Force -Recurse -ErrorAction Stop
  }
}
if(-not $pass){throw 'CONSOLE_CI_NOT_QUALIFIED'}
Write-Output 'C545D_CONSOLE_STOP_BASELINE_PASS,source_worker_handler_exact=1,gui_stop_order=1,marker_before_event=1,ctrlc_event=1,worker_survived_ctrlc=1,owned_rollback=1,real_recorder_executed=0,real_camera=0,install_approved=0'
