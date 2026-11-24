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
    [StructLayout(LayoutKind.Sequential)]
    struct Association { public IntPtr Key, Port; }
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern IntPtr CreateIoCompletionPort(IntPtr file,IntPtr existing,IntPtr key,uint threads);
    [DllImport("kernel32.dll", SetLastError=true)]
    [return:MarshalAs(UnmanagedType.Bool)]
    static extern bool SetInformationJobObject(IntPtr job,int cls,ref Association info,uint len);
    [DllImport("kernel32.dll", SetLastError=true)]
    [return:MarshalAs(UnmanagedType.Bool)]
    static extern bool GetQueuedCompletionStatus(IntPtr port,out uint msg,out IntPtr key,out IntPtr value,uint ms);
    IntPtr handle, port;
    public C545DNamerAccountingJob(){
        handle=CreateJobObject(IntPtr.Zero,null);
        if(handle==IntPtr.Zero)throw new Win32Exception(Marshal.GetLastWin32Error());
        try {
            port=CreateIoCompletionPort(new IntPtr(-1),IntPtr.Zero,IntPtr.Zero,1);
            if(port==IntPtr.Zero)throw new Win32Exception(Marshal.GetLastWin32Error());
            Association a=new Association { Key=new IntPtr(1), Port=port };
            if(!SetInformationJobObject(handle,7,ref a,(uint)Marshal.SizeOf(typeof(Association))))
                throw new Win32Exception(Marshal.GetLastWin32Error());
        } catch { Dispose(); throw; }
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
    // Notifications are best effort; exact reconciliation is mandatory.
    public uint[] NewProcesses(){
        var ids=new System.Collections.Generic.List<uint>();
        for(int i=0;i<4096;i++){
            uint msg; IntPtr key,value;
            if(!GetQueuedCompletionStatus(port,out msg,out key,out value,250)){
                if(Marshal.GetLastWin32Error()==258)return ids.ToArray();
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
            if(key!=new IntPtr(1))throw new InvalidOperationException("Unexpected job key");
            if(msg==6)ids.Add(checked((uint)value.ToInt64()));
        }
        throw new InvalidOperationException("Notification bound exceeded");
    }
    public void Dispose(){
        if(handle!=IntPtr.Zero){CloseHandle(handle);handle=IntPtr.Zero;}
        if(port!=IntPtr.Zero){CloseHandle(port);port=IntPtr.Zero;}
    }
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
    $proc=$null;$job=$null;$traceId=$null;$etl=$null;$traceRunning=$false
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
        # Private disposable ETW session; no event payload is uploaded or printed.
        # Calibrate with a known outside-job process and require its start/stop.
        $traceId='C545D_CI_KernelProc_'+[guid]::NewGuid().ToString('N')
        $etl=Join-Path $arm 'private-process.etl'
        & logman.exe start $traceId -p '{22FB2CD6-0E7B-422B-A0C7-2FAD1FD0E716}' 0x10 4 -o $etl -nb 16 64 -bs 64 -ets *> $null
        if($LASTEXITCODE -ne 0){throw 'NAMER_OVERHEAD_ETW_START'}
        $traceRunning=$true
        $calPsi=New-Object Diagnostics.ProcessStartInfo
        $calPsi.FileName=Join-Path $env:SystemRoot 'System32\cmd.exe'
        $calPsi.Arguments='/d /c exit 0';$calPsi.UseShellExecute=$false;$calPsi.CreateNoWindow=$true
        $cal=[Diagnostics.Process]::Start($calPsi)
        try{
            $calId=[uint32]$cal.Id
            if(-not $cal.WaitForExit(5000) -or $cal.ExitCode -ne 0){throw 'NAMER_OVERHEAD_ETW_CALIBRATION_PROCESS'}
        }finally{if(-not $cal.HasExited){$cal.Kill();[void]$cal.WaitForExit(3000)};$cal.Dispose()}
        # Completion port is associated while job is empty, before attaching helper.
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
        $batchEndMs=$clock.ElapsedMilliseconds
        # Membership from job notifications, identity and lifetime from ETW.
        # Never infer membership from a wall-clock filter or a stale parent PID.
        $traceQualified=$false
        $probeStarts=0;$conhostStarts=0;$otherStarts=0;$directProbes=0
        $missing=0;$ambiguous=0;$badLifetime=0;$calOk=0;$jobIds=@()
        try{
            $jobIds=@($job.NewProcesses())
            & logman.exe stop $traceId -ets *> $null
            if($LASTEXITCODE -ne 0){throw 'NAMER_OVERHEAD_ETW_STOP'}
            $traceRunning=$false
            $unique=@($jobIds|Sort-Object -Unique)
            $wanted=New-Object 'System.Collections.Generic.HashSet[uint32]'
            foreach($id in $unique){[void]$wanted.Add([uint32]$id)}
            [void]$wanted.Add($calId)
            $starts=@{};$ends=@{}
            foreach($event in (Get-WinEvent -Path $etl -Oldest -ErrorAction Stop)){
                try{
                    if($event.ProviderName -ne 'Microsoft-Windows-Kernel-Process' -or $event.Id -notin @(1,2)){continue}
                    [xml]$xml=$event.ToXml()
                    $d=@{}
                    foreach($node in $xml.Event.EventData.Data){$d[[string]$node.Name]=[string]$node.'#text'}
                    if(-not $d.ContainsKey('ProcessID')){continue}
                    $id=[uint32]$d['ProcessID']
                    if(-not $wanted.Contains($id)){continue}
                    $record=@{create=$d['CreateTime'];seq=$d['ProcessSequenceNumber'];parent=$d['ParentProcessID'];image=$d['ImageName']}
                    $table=if($event.Id -eq 1){$starts}else{$ends}
                    if(-not $table.ContainsKey($id)){$table[$id]=@()}
                    $table[$id]+=$record
                }finally{$event.Dispose()}
            }
            function Test-Lifetime([uint32]$id){
                if(@($starts[$id]).Count -ne 1 -or @($ends[$id]).Count -ne 1){return $false}
                $st=$starts[$id][0];$en=$ends[$id][0]
                return (-not [string]::IsNullOrEmpty($st.create) -and $st.create -ceq $en.create -and
                    ((-not $st.seq -and -not $en.seq) -or ($st.seq -and $st.seq -ceq $en.seq)))
            }
            if((Test-Lifetime $calId) -and [uint32]$starts[$calId][0].parent -eq [uint32]$PID -and
                [IO.Path]::GetFileName($starts[$calId][0].image) -ieq 'cmd.exe' -and $calId -notin $unique){$calOk=1}
            foreach($id in $unique){
                if($id -eq [uint32]$proc.Id){continue}
                if(-not $starts.ContainsKey($id) -or -not $ends.ContainsKey($id)){$missing++;continue}
                if($starts[$id].Count -ne 1 -or $ends[$id].Count -ne 1){$ambiguous++;continue}
                if(-not(Test-Lifetime $id)){$badLifetime++;continue}
                $st=$starts[$id][0]
                $image=[IO.Path]::GetFileName($st.image)
                if($image -ieq 'ffprobe.exe'){
                    $probeStarts++
                    if([uint32]$st.parent -eq [uint32]$proc.Id){$directProbes++}
                }elseif($image -ieq 'conhost.exe'){$conhostStarts++}
                else{$otherStarts++}
            }
            $traceQualified=($calOk -eq 1 -and $jobIds.Count -eq $batch.Total -and $unique.Count -eq $jobIds.Count -and
                [uint32]$proc.Id -in $unique -and $missing -eq 0 -and $ambiguous -eq 0 -and $badLifetime -eq 0 -and
                $probeStarts -eq $segments -and $directProbes -eq $segments -and $otherStarts -eq 0 -and
                (1+$probeStarts+$conhostStarts) -eq $batch.Total)
        }catch{Write-Host 'C545D_NAMER_OVERHEAD_ETW_ERROR,detail_suppressed=1'}
        $unreconciled=[long]$batch.Total-1-$probeStarts-$conhostStarts-$otherStarts
        Write-Host ('C545D_NAMER_OVERHEAD_PROCESS_TRACE,arm='+$name+',job_total='+$batch.Total+
            ',direct_ffprobe='+$directProbes+',descendant_ffprobe='+$probeStarts+',descendant_conhost='+$conhostStarts+
            ',descendant_other='+$otherStarts+',unreconciled='+$unreconciled+',active='+$batch.Active+
            ',job_notifications='+$jobIds.Count+',calibration='+$calOk+',missing_lifetime='+$missing+
            ',ambiguous_lifetime='+$ambiguous+',bad_lifetime='+$badLifetime+',etw=1')
        Assert-Equal $batch.Active 1 'ONLY_HELPER_REMAINS'
        $batchMs=$batchEndMs
        [IO.File]::WriteAllText($stop,'CI_TEST')
        if(-not $proc.WaitForExit(20000)){throw 'NAMER_OVERHEAD_STOP'}
        Assert-Equal $proc.ExitCode 0 'EXIT'
        if(-not $stdout.Wait(1000) -or -not $stderr.Wait(1000)){throw 'NAMER_OVERHEAD_PIPE'}
        $final=$job.Read()
        Assert-Equal $final.Total $batch.Total 'FINAL_PROCESS_COUNT'
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
            ',media_hashes='+$segments+',trace_qualified='+[int]$traceQualified+',real_camera=0')
        if(-not $traceQualified){throw 'NAMER_OVERHEAD_PROCESS_TRACE_UNQUALIFIED'}
    }finally{
        if($proc){if(-not $proc.HasExited){$proc.Kill();[void]$proc.WaitForExit(3000)};$proc.Dispose()}
        if($job){$job.Dispose()}
        if($traceRunning){& logman.exe stop $traceId -ets *> $null}
        if($etl -and (Test-Path -LiteralPath $etl)){Remove-Item -LiteralPath $etl -Force}
        foreach($k in $old.Keys){[Environment]::SetEnvironmentVariable($k,$old[$k],'Process')}
    }
}
$failed=0
foreach($name in @('a1','b1','b2','a2')){
    try{Run-Arm $name ($name.StartsWith('b'))}
    catch{
        $failed++
        $reason=[string]$_.Exception.Message
        if($reason -cnotmatch '^NAMER_OVERHEAD_[A-Z_]+(?: actual=-?\d+ expected=-?\d+)?$'){$reason='UNCLASSIFIED'}
        Write-Host ('C545D_NAMER_OVERHEAD_ARM_FAIL,arm='+$name+',reason='+$reason)
    }
}
if($failed -ne 0){throw ('NAMER_OVERHEAD_ABBA_UNQUALIFIED failed_arms='+$failed)}
Write-Host 'C545D_NAMER_OVERHEAD_ABBA_PASS,arms=4,segments_per_arm=8,same_runner=1,actual_namer=1,real_probe=1,tree_cpu=1,exact_probe_process_count=1,job_count_reconciled=1,short_fixture_only=1,real_camera=0,install_approved=0'
