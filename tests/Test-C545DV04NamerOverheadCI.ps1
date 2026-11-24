# CI-only controlled same-runner ABBA, actual namer and real pinned ffprobe.
# The job is accounting-only: no limits, no kill-on-close, no host changes.
param([Parameter(Mandatory=$true)][string]$FixtureDirectory,
      [Parameter(Mandatory=$true)][string]$ProbeExe)
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows'){throw 'CI_ONLY'}
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public sealed class C545DNamerAccountingJob : IDisposable {
    [StructLayout(LayoutKind.Sequential)]
    public struct Accounting {
        public long User, Kernel, PeriodUser, PeriodKernel;
        public uint Faults, Total, Active, Terminated;
        public long CpuTicks { get { return checked(User+Kernel); } }
    }
    [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    static extern IntPtr CreateJobObject(IntPtr attributes,string name);
    [DllImport("kernel32.dll", SetLastError=true)]
    [return:MarshalAs(UnmanagedType.Bool)]
    static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    [DllImport("kernel32.dll", SetLastError=true)]
    [return:MarshalAs(UnmanagedType.Bool)]
    static extern bool QueryInformationJobObject(IntPtr job,int cls,out Accounting info,uint len,out uint returned);
    [DllImport("kernel32.dll", SetLastError=true)]
    [return:MarshalAs(UnmanagedType.Bool)]
    static extern bool CloseHandle(IntPtr handle);
    IntPtr handle;
    public C545DNamerAccountingJob(){
        handle=CreateJobObject(IntPtr.Zero,null);
        if(handle==IntPtr.Zero)throw new Win32Exception(Marshal.GetLastWin32Error());
    }
    public void Attach(IntPtr process){
        if(!AssignProcessToJobObject(handle,process))throw new Win32Exception(Marshal.GetLastWin32Error());
    }
    public Accounting Read(){
        Accounting a; uint got;
        if(!QueryInformationJobObject(handle,1,out a,(uint)Marshal.SizeOf(typeof(Accounting)),out got))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        return a;
    }
    public void Dispose(){if(handle!=IntPtr.Zero){CloseHandle(handle);handle=IntPtr.Zero;}}
}
'@
$repo=Split-Path -Parent $PSScriptRoot
$root=Join-Path $FixtureDirectory 'namer-overhead-abba'
New-Item -ItemType Directory -Path $root|Out-Null
$sample=Join-Path $FixtureDirectory '2026-11-24_12-00_12-01.mp4'
$hash=(Get-FileHash -LiteralPath $sample).Hash
$probeHash=(Get-FileHash -LiteralPath $ProbeExe).Hash
$segments=8
function Assert-Equal($a,$b,[string]$tag){if($a -cne $b){throw ('NAMER_OVERHEAD_'+$tag+' actual='+$a+' expected='+$b)}}
function Run-Arm([string]$name,[bool]$enabled){
    $arm=Join-Path $root $name
    $output=Join-Path $arm 'output';$local=Join-Path $arm 'local'
    foreach($d in @($output,$local)){New-Item -ItemType Directory -Path $d -Force|Out-Null}
    $ready=Join-Path $arm 'ready';$stop=Join-Path $arm 'stop'
    $old=@{}
    foreach($k in @('PATH','LOCALAPPDATA','C545D_METADATA_V04','C545D_METADATA_PROBE_SHA256')){
        $old[$k]=[Environment]::GetEnvironmentVariable($k,'Process')
    }
    $env:PATH=(Split-Path -Parent $ProbeExe)+';'+$old['PATH']
    $env:LOCALAPPDATA=$local
    $env:C545D_METADATA_V04=$null;$env:C545D_METADATA_PROBE_SHA256=$null
    if($enabled){$env:C545D_METADATA_V04='1';$env:C545D_METADATA_PROBE_SHA256=$probeHash}
    $proc=$null;$job=$null
    try{
        Assert-Equal (Get-Command ffprobe.exe -ErrorAction Stop).Source $ProbeExe 'DIRECT_PROBE'
        $psi=New-Object Diagnostics.ProcessStartInfo
        $psi.FileName=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $psi.Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+(Join-Path $repo 'SegmentNamerWorker.ps1')+
            '" -OutputDirectory "'+$output+'" -OwnerProcessId '+$PID+' -ReadyFile "'+$ready+'" -StopFile "'+$stop+'"'
        $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true
        $psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
        $startup=[Diagnostics.Stopwatch]::StartNew()
        $proc=[Diagnostics.Process]::Start($psi);$null=$proc.Handle
        $stdout=$proc.StandardOutput.ReadToEndAsync();$stderr=$proc.StandardError.ReadToEndAsync()
        while(-not(Test-Path -LiteralPath $ready)){
            if($proc.HasExited -or $startup.ElapsedMilliseconds -gt 20000){throw 'NAMER_OVERHEAD_READY'}
            Start-Sleep -Milliseconds 50
        }
        $startupMs=$startup.ElapsedMilliseconds
        # Attach AFTER initialization/ready, BEFORE any fixture is submitted.
        # Counts include terminated ffprobe descendants missed by polling.
        $job=New-Object C545DNamerAccountingJob
        $job.Attach($proc.Handle)
        $before=$job.Read()
        Assert-Equal $before.Total 1 'INITIAL_JOB_COUNT'
        $proc.Refresh()
        $cpuFirst=$proc.TotalProcessorTime.Ticks
        $privateFirst=$proc.PrivateMemorySize64;$handlesFirst=$proc.HandleCount
        $privatePeak=$privateFirst;$handlesPeak=$handlesFirst
        $latencies=@()
        $clock=[Diagnostics.Stopwatch]::StartNew()
        for($i=1;$i -le $segments;$i++){
            $leaf=('C545D_PENDING_20261124_120000_12345678_{0:D5}.mp4' -f $i)
            $pending=Join-Path $output $leaf
            # Copy identical content outside the watched directory, then move it in.
            $staged=Join-Path $arm 'incoming.mp4'
            Copy-Item -LiteralPath $sample -Destination $staged
            $one=[Diagnostics.Stopwatch]::StartNew()
            Move-Item -LiteralPath $staged -Destination $pending
            do{
                if($proc.HasExited -or $one.ElapsedMilliseconds -gt 15000){throw 'NAMER_OVERHEAD_RENAME'}
                $proc.Refresh()
                $privatePeak=[Math]::Max($privatePeak,$proc.PrivateMemorySize64)
                $handlesPeak=[Math]::Max($handlesPeak,$proc.HandleCount)
                if(-not(Test-Path -LiteralPath $pending)){break}
                Start-Sleep -Milliseconds 50
            }while($true)
            $latencies+= $one.ElapsedMilliseconds
        }
        # Allow the last post-rename journal publish to complete; identical
        # fixed settling time in both arms, not an assumed writer completion.
        Start-Sleep -Milliseconds 500
        $proc.Refresh()
        $cpuLast=$proc.TotalProcessorTime.Ticks
        $privateLast=$proc.PrivateMemorySize64;$handlesLast=$proc.HandleCount
        $privatePeak=[Math]::Max($privatePeak,$privateLast)
        $handlesPeak=[Math]::Max($handlesPeak,$handlesLast)
        $batch=$job.Read()
        Assert-Equal $batch.Total ($segments+1) 'EXACT_ONE_CHILD_PER_SEGMENT'
        Assert-Equal $batch.Active 1 'ONLY_HELPER_REMAINS'
        $batchMs=$clock.ElapsedMilliseconds
        [IO.File]::WriteAllText($stop,'CI_TEST')
        if(-not $proc.WaitForExit(20000)){throw 'NAMER_OVERHEAD_STOP'}
        Assert-Equal $proc.ExitCode 0 'EXIT'
        if(-not $stdout.Wait(1000) -or -not $stderr.Wait(1000)){throw 'NAMER_OVERHEAD_PIPE'}
        $final=$job.Read()
        Assert-Equal $final.Total ($segments+1) 'FINAL_PROCESS_COUNT'
        $files=@(Get-ChildItem -LiteralPath $output -File)
        Assert-Equal $files.Count $segments 'FILES'
        foreach($file in $files){
            if($file.Name -like 'C545D_PENDING_*'){throw 'NAMER_OVERHEAD_PENDING_REMAINS'}
            Assert-Equal (Get-FileHash -LiteralPath $file.FullName).Hash $hash 'HASH'
        }
        $store=Join-Path $local 'C545D_GStreamer\MetadataV04'
        if($enabled){
            $expected='C545D_METADATA_V04_STOP,drained=1,accepted='+$segments+',saved='+$segments+',rejected=0,failed=0,receipt=final_saved,publish_errors=0'
            if(-not $stdout.Result.Contains($expected)){throw 'NAMER_OVERHEAD_WRITER'}
            $j=@(Get-ChildItem -LiteralPath (Join-Path $store 'journal') -File)
            Assert-Equal $j.Count 1 'JOURNAL'
            $rows=@(Get-Content -LiteralPath $j[0].FullName)
            Assert-Equal $rows.Count ($segments+1) 'ROWS'
            foreach($row in @($rows|Select-Object -Skip 1)){
                if($row -cnotmatch '\|profile_match_metadata_only\|'){throw 'NAMER_OVERHEAD_PROFILE'}
            }
        }elseif(Test-Path -LiteralPath $store){throw 'NAMER_OVERHEAD_OFF_STORAGE'}
        $jobCpu=[long][Math]::Round(($batch.CpuTicks-$before.CpuTicks)/10000.0)
        $helperCpu=[long][Math]::Round(($cpuLast-$cpuFirst)/10000.0)
        if($jobCpu -lt 0 -or $helperCpu -lt 0){throw 'NAMER_OVERHEAD_CPU_NEGATIVE'}
        $mode=if($enabled){'on'}else{'off'}
        $maxLatency=($latencies|Measure-Object -Maximum).Maximum
        Write-Host ('C545D_NAMER_OVERHEAD_ARM,arm='+$name+',mode='+$mode+',segments='+$segments+
            ',startup_ms='+$startupMs+',batch_ms='+$batchMs+',max_rename_ms='+$maxLatency+
            ',tree_cpu_ms='+$jobCpu+',helper_cpu_ms='+$helperCpu+',tree_processes='+$batch.Total+
            ',private_first_b='+$privateFirst+',private_last_b='+$privateLast+',private_sample_peak_b='+$privatePeak+
            ',handles_first='+$handlesFirst+',handles_last='+$handlesLast+',handles_sample_peak='+$handlesPeak+
            ',media_hashes='+$segments+',real_camera=0')
    }finally{
        if($proc){if(-not $proc.HasExited){$proc.Kill();[void]$proc.WaitForExit(3000)};$proc.Dispose()}
        if($job){$job.Dispose()}
        foreach($k in $old.Keys){[Environment]::SetEnvironmentVariable($k,$old[$k],'Process')}
    }
}
Run-Arm 'a1' $false
Run-Arm 'b1' $true
Run-Arm 'b2' $true
Run-Arm 'a2' $false
Write-Host 'C545D_NAMER_OVERHEAD_ABBA_PASS,arms=4,segments_per_arm=8,same_runner=1,actual_namer=1,real_probe=1,tree_cpu=1,exact_probe_process_count=1,short_fixture_only=1,real_camera=0,install_approved=0'
