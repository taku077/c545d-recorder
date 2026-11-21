#Requires -Version 5.1
<#
 Windows CI ONLY. Reproduce the real GUI's stop-marker + CTRL_C_EVENT
 protocol for ONE owned synthetic RecordGUIWorker with a private console.
 Reject any target console that includes a process outside the owned worker,
 its private GStreamer gst-launch, and this sender. Never usable on a
 recording host and never searches or signals a user's processes.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$StageRoot,
  [Parameter(Mandatory=$true)][int]$WorkerPid,
  [Parameter(Mandatory=$true)][string]$SessionId
)
$ErrorActionPreference='Stop'
$phase='CI_GATE';$signalSent=$false
try {
  if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
     -not $env:RUNNER_TEMP){throw 'NOT_GITHUB_WINDOWS_CI'}
  $root=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
  $stage=[IO.Path]::GetFullPath($StageRoot).TrimEnd('\')
  if(-not [string]::Equals([IO.Path]::GetDirectoryName($stage).TrimEnd('\'),
      $root,[StringComparison]::OrdinalIgnoreCase) -or
     [IO.Path]::GetFileName($stage) -cnotmatch '^c545d-ci-production-mirror-[a-f0-9]{32}$' -or
     $SessionId -cnotmatch '^[a-f0-9]{32}$' -or $WorkerPid -le 0){
    throw 'INVALID_OWNED_STAGE'
  }
  $stageItem=Get-Item -LiteralPath $stage -Force
  if(-not $stageItem.PSIsContainer -or
     ($stageItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
     [IO.File]::ReadAllText((Join-Path $stage '.c545d-ci-owned')) -cne
     'CI_MIRROR_ONLY_NOT_FOR_EXECUTION'){throw 'UNOWNED_STAGE'}
  $dir=Join-Path $stage 'ci-localappdata\C545D_GStreamer\Control'
  $ready=Join-Path $dir ('session_'+$SessionId+'.ready')
  $stop=Join-Path $dir ('session_'+$SessionId+'.stop')
  if(-not (Test-Path -LiteralPath $ready -PathType Leaf) -or
     [IO.File]::ReadAllText($ready).Trim() -cne [string]$WorkerPid -or
     (Test-Path -LiteralPath $stop)){throw 'WORKER_READY_MISMATCH'}
  $worker=Get-Process -Id $WorkerPid -ErrorAction Stop
  try {
    $workerExe=[IO.Path]::GetFullPath($worker.Path)
    $expectedPs=[IO.Path]::GetFullPath(
      (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'))
    if(-not [string]::Equals($workerExe,$expectedPs,
           [StringComparison]::OrdinalIgnoreCase)){throw 'WORKER_EXECUTABLE_UNEXPECTED'}
  } finally {$worker.Dispose()}
  $phase='ATTACH_WORKER_CONSOLE'
  Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class C545DOnlyCiConsoleSignal {
  [DllImport("kernel32.dll",SetLastError=true)]
  public static extern bool FreeConsole();
  [DllImport("kernel32.dll",SetLastError=true)]
  public static extern bool AttachConsole(uint pid);
  [DllImport("kernel32.dll",SetLastError=true)]
  public static extern uint GetConsoleProcessList([Out] uint[] processes,uint count);
  [DllImport("kernel32.dll",SetLastError=true)]
  public static extern bool SetConsoleCtrlHandler(IntPtr handler,bool add);
  [DllImport("kernel32.dll",SetLastError=true)]
  public static extern bool GenerateConsoleCtrlEvent(uint signal,uint group);
}
'@
  # GUI semantics: marker committed before signalling, so a failed signal
  # can never turn into an unmarked auto-reconnect.
  [IO.File]::WriteAllText($stop,'CI_GUI_CTRL_C_STOP_MARKER')
  [void][C545DOnlyCiConsoleSignal]::FreeConsole()
  if(-not [C545DOnlyCiConsoleSignal]::AttachConsole([uint32]$WorkerPid)){
    throw 'NO_PRIVATE_WORKER_CONSOLE'
  }
  try {
    $processes=New-Object uint32[] 32
    $count=[C545DOnlyCiConsoleSignal]::GetConsoleProcessList(
           $processes,[uint32]$processes.Length)
    if($count -lt 2 -or $count -gt 3){throw 'CONSOLE_NOT_STRICTLY_OWNED'}
    $foundWorker=$false;$foundSender=$false;$gstSeen=0
    $expectedGst=[IO.Path]::GetFullPath((Join-Path $stage 'bin\gst-launch-1.0.exe'))
    for($i=0;$i -lt $count;$i++){
      $pidValue=[int]$processes[$i]
      if($pidValue -eq $WorkerPid){$foundWorker=$true;continue}
      if($pidValue -eq $PID){$foundSender=$true;continue}
      $other=Get-Process -Id $pidValue -ErrorAction Stop
      try {
        if(-not [string]::Equals([IO.Path]::GetFullPath($other.Path),
             $expectedGst,[StringComparison]::OrdinalIgnoreCase)){
          throw 'CONSOLE_CONTAINS_UNOWNED_PROCESS'
        }
      } finally {$other.Dispose()}
      $gstSeen++
    }
    if(-not $foundWorker -or -not $foundSender -or $gstSeen -ne 1){
      throw 'CONSOLE_GSTREAMER_NOT_READY'
    }
    $phase='CTRL_C_SEND'
    if(-not [C545DOnlyCiConsoleSignal]::SetConsoleCtrlHandler(
        [IntPtr]::Zero,$true)){throw 'SIGNAL_SENDER_NOT_PROTECTED'}
    if(-not [C545DOnlyCiConsoleSignal]::GenerateConsoleCtrlEvent(0,0)){
      throw 'CTRL_C_SEND_FAILED'
    }
    $signalSent=$true
    Start-Sleep -Milliseconds 350
  } finally {
    [void][C545DOnlyCiConsoleSignal]::FreeConsole()
  }
} catch {
  $known=@('NOT_GITHUB_WINDOWS_CI','INVALID_OWNED_STAGE','UNOWNED_STAGE',
    'WORKER_READY_MISMATCH','WORKER_EXECUTABLE_UNEXPECTED',
    'NO_PRIVATE_WORKER_CONSOLE','CONSOLE_NOT_STRICTLY_OWNED',
    'CONSOLE_CONTAINS_UNOWNED_PROCESS','CONSOLE_GSTREAMER_NOT_READY',
    'SIGNAL_SENDER_NOT_PROTECTED','CTRL_C_SEND_FAILED')
  $reason=if($_.Exception.Message -in $known){$_.Exception.Message}else{'BLOCKED'}
  Write-Output "C545D_CI_GUI_CTRL_SIGNAL_FAIL,phase=$phase,reason=$reason,real_camera=0"
  exit 3
}
if(-not $signalSent){exit 3}
Write-Output 'C545D_CI_GUI_CTRL_SIGNAL_PASS,stop_marker=1,console_owned=1,gst_launch_owned=1,ctrl_c_sent=1,real_camera=0'
exit 0
