# CI-only external HWND button driver. Never sends global input or modifies EXE.
param([int]$TargetPid,[ValidateSet('start','stop','quit')][string]$Action,[string]$Stage)
$ErrorActionPreference='Stop'
$phase='GUARD'
$main=0;$buttons=0;$matched=0;$enabled=0;$sent=0;$winerr=0
$target=$null
try{
 if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
    $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Stage)) -ine [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\') -or
    [IO.Path]::GetFileName($Stage) -cnotmatch '^c545d-ci-production-mirror-[a-f0-9]{32}$' -or
    [IO.File]::ReadAllText((Join-Path $Stage '.c545d-ci-owned')) -cne 'CI_MIRROR_ONLY_NOT_FOR_EXECUTION'){throw 'GUARD'}
 $phase='PROCESS'
 $target=Get-Process -Id $TargetPid -ErrorAction Stop
 if($target.Path -ine (Join-Path $Stage 'C545D_Recorder.exe') -or $target.SessionId -ne (Get-Process -Id $PID).SessionId){throw 'PROCESS'}
 $phase='COMPILE'
 Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class C545DExternalButtons {
 delegate bool EnumProc(IntPtr h,IntPtr l);
 [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f,IntPtr l);
 [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr h,EnumProc f,IntPtr l);
 [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h,StringBuilder b,int n);
 [DllImport("user32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr SendMessageTimeout(IntPtr h,uint m,IntPtr w,StringBuilder l,uint f,uint t,out IntPtr result);
 [DllImport("user32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr SendMessageTimeout(IntPtr h,uint m,IntPtr w,IntPtr l,uint f,uint t,out IntPtr result);
 [DllImport("user32.dll")] static extern bool IsWindowEnabled(IntPtr h);
 [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] static extern bool IsChild(IntPtr parent,IntPtr child);
 public sealed class Result {
  public int Main,Buttons,Matched,Enabled,Sent,Error;
 }
 static bool Owned(IntPtr h,uint p){uint id;return GetWindowThreadProcessId(h,out id)!=0&&id==p;}
 static string Class(IntPtr h){var b=new StringBuilder(256);GetClassName(h,b,b.Capacity);return b.ToString();}
 static string Caption(IntPtr h){var b=new StringBuilder(256);IntPtr r;return SendMessageTimeout(h,13,(IntPtr)b.Capacity,b,2,500,out r)==IntPtr.Zero?null:b.ToString();}
 public static Result Click(uint pid,string label){
  var r=new Result();var roots=new List<IntPtr>();
  EnumWindows((h,l)=>{if(Owned(h,pid)&&IsWindowVisible(h)&&Class(h).StartsWith("WindowsForms10.Window.",StringComparison.Ordinal))roots.Add(h);return true;},IntPtr.Zero);
  r.Main=roots.Count;
  if(roots.Count!=1)return r;
  IntPtr root=roots[0];var hits=new List<IntPtr>();
  EnumChildWindows(root,(h,l)=>{
    if(Owned(h,pid)&&Class(h).StartsWith("WindowsForms10.BUTTON.",StringComparison.Ordinal)){
     r.Buttons++;if(Caption(h)==label)hits.Add(h);
    }return r.Buttons<64;
  },IntPtr.Zero);
  r.Matched=hits.Count;
  if(hits.Count!=1||r.Buttons>=64)return r;
  IntPtr button=hits[0];
  if(!Owned(root,pid)||!Owned(button,pid)||!IsChild(root,button)||!IsWindowVisible(button)||!IsWindowEnabled(root)||!IsWindowEnabled(button))return r;
  r.Enabled=1;
  IntPtr result;
  // Never retry an attempted click, even on timeout. Caller independently
  // proves actual worker launch/stop marker/EOS/exit.
  r.Sent=SendMessageTimeout(button,0x00F5,IntPtr.Zero,IntPtr.Zero,2,8000,out result)!=IntPtr.Zero?1:-1;
  if(r.Sent<0)r.Error=Marshal.GetLastWin32Error();
  return r;
 }
}
'@
    $names=@{
        start=(-join @([char]9679,[char]32,[char]37682,[char]30011,[char]38283,[char]22987))
        stop=(-join @([char]9632,[char]32,[char]37682,[char]30011,[char]20572,[char]27490))
        quit=(-join @([char]12450,[char]12503,[char]12522,[char]12434,[char]32066,[char]20102))
    }
 $phase='FIND'
 $clock=[Diagnostics.Stopwatch]::StartNew()
 do{
    $target.Refresh()
    if($target.HasExited){throw 'TARGET_EXITED'}
    $r=[C545DExternalButtons]::Click([uint32]$TargetPid,$names[$Action])
    $main=$r.Main;$buttons=$r.Buttons;$matched=$r.Matched;$enabled=$r.Enabled;$sent=$r.Sent;$winerr=$r.Error
    if($sent -eq 1){$phase='PASS';break}
    if($sent -eq -1 -or $main -gt 1 -or $matched -gt 1){throw 'AMBIGUOUS_OR_TIMEOUT'}
    Start-Sleep -Milliseconds 150
 }while($clock.ElapsedMilliseconds -lt 12000)
 if($phase -ne 'PASS'){throw 'BUTTON_NOT_READY'}
}catch{}finally{
 if($target){$target.Dispose()}
 [IO.File]::WriteAllText((Join-Path $Stage ('ci-button-'+$Action+'.txt')),
   ('C545D_PACKAGED_BUTTON_DIAG,action='+$Action+',phase='+$phase+',main='+$main+',buttons='+$buttons+',matched='+$matched+',enabled='+$enabled+',sent='+$sent+',winerr='+$winerr))
}
if($phase -eq 'PASS'){exit 0}else{exit 3}
