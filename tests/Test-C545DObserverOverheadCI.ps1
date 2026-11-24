# CI-only same-runner ABBA: exact ZIP observer with a live synthetic Gst process.
# Sampling interval accelerated from default 60s to 10s; no real RTSP or camera.
param([Parameter(Mandatory=$true)][string]$BundleZip,
      [Parameter(Mandatory=$true)][string]$SdkRoot)
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or -not $env:RUNNER_TEMP){throw 'CI_ONLY'}
$root=Join-Path $env:RUNNER_TEMP ('c545d-observer-abba-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root|Out-Null
$pkg=Join-Path $root 'package'
Expand-Archive -LiteralPath $BundleZip -DestinationPath $pkg
$source=Join-Path $pkg 'diagnostics\C545D-WeeklyObserver.ps1'
$id=Get-Content -LiteralPath (Join-Path $pkg 'BUILD_IDENTITY.json') -Raw|ConvertFrom-Json
$hash=(Get-FileHash -LiteralPath $source).Hash
if($hash -cne $id.files.'diagnostics/C545D-WeeklyObserver.ps1' -or
   $hash -cne (Get-FileHash -LiteralPath 'diagnostics/C545D-WeeklyObserver.ps1').Hash -or
   $id.source_commit -cne $env:GITHUB_SHA){throw 'OBSERVER_PACKAGE_IDENTITY'}
$gst=Join-Path $SdkRoot 'bin\gst-launch-1.0.exe'
$ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$old=@{}
foreach($k in @('PATH','GST_PLUGIN_PATH','GST_PLUGIN_PATH_1_0','GST_PLUGIN_SYSTEM_PATH','GST_PLUGIN_SYSTEM_PATH_1_0','GST_REGISTRY')){
    $old[$k]=[Environment]::GetEnvironmentVariable($k,'Process')
}
function Snapshot($p){
    $p.Refresh()
    if($p.HasExited){throw 'OWNED_PROCESS_EXITED'}
    return [pscustomobject]@{cpu=[long]$p.TotalProcessorTime.Ticks;private=[long]$p.PrivateMemorySize64;handles=[int]$p.HandleCount}
}
function Start-Owned([string]$exe,[string[]]$argList,[string]$prefix){
    $p=Start-Process -FilePath $exe -ArgumentList $argList -PassThru -WindowStyle Hidden -RedirectStandardOutput ($prefix+'.out') -RedirectStandardError ($prefix+'.err')
    $null=$p.Handle
    return $p
}
function Close-Owned($p){
    if($p){try{if(-not $p.HasExited){$p.Kill();[void]$p.WaitForExit(5000)}}finally{$p.Dispose()}}
}
function Run-Arm([string]$name,[bool]$enabled){
    $dir=Join-Path $root $name
    $store=Join-Path $dir 'observer'
    New-Item -ItemType Directory -Path $dir|Out-Null
    $g=$null;$o=$null;$e=$null
    try{
        $other=@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue)
        try{if($other.Count){throw 'OTHER_GSTREAMER_PROCESS'}}finally{foreach($p in $other){$p.Dispose()}}
        # The identical CPU workload is live paced. Not a full production recording.
        $g=Start-Owned $gst @('-q','videotestsrc','is-live=true','pattern=smpte','!','video/x-raw,width=1280,height=720,framerate=15/1','!','x264enc','speed-preset=medium','quantizer=24','pass=quant','!','fakesink','sync=true') (Join-Path $dir 'gst')
        Start-Sleep -Seconds 3
        $first=Snapshot $g
        $clock=[Diagnostics.Stopwatch]::StartNew()
        if($enabled){
            $argsCommon=@('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',('"'+$source+'"'),
                '-RootDirectory',('"'+$store+'"'),'-RecorderLogDirectory',('"'+(Join-Path $dir 'missing-logs')+'"'),
                '-MetadataJournalRoot',('"'+(Join-Path $dir 'missing-journal')+'"'),'-WriterReceiptRoot',('"'+(Join-Path $dir 'missing-receipts')+'"'))
            $o=Start-Owned $ps ($argsCommon+@('-IntervalSeconds','10')) (Join-Path $dir 'sampler')
        }
        $firstO=$null;$lastO=$null;$peakPrivate=0L;$peakHandles=0
        while($clock.ElapsedMilliseconds -lt 35000){
            if($g.HasExited){throw 'GST_EXITED'}
            if($enabled){
                $lastO=Snapshot $o
                if($null -eq $firstO){$firstO=$lastO}
                $peakPrivate=[Math]::Max($peakPrivate,$lastO.private)
                $peakHandles=[Math]::Max($peakHandles,$lastO.handles)
            }
            Start-Sleep -Milliseconds 500
        }
        $last=Snapshot $g
        $elapsed=$clock.ElapsedMilliseconds
        $sampleCount=0;$observerCpu=0L;$observerPrivateFirst=0L;$observerPrivateLast=0L;$observerHandlesFirst=0;$observerHandlesLast=0
        $exportCpu=0L;$exportMs=0L
        if($enabled){
            $lastO=Snapshot $o
            $observerCpu=[long][Math]::Round($lastO.cpu/10000.0)
            $observerPrivateFirst=$firstO.private;$observerPrivateLast=$lastO.private
            $observerHandlesFirst=$firstO.handles;$observerHandlesLast=$lastO.handles
            $peakPrivate=[Math]::Max($peakPrivate,$lastO.private);$peakHandles=[Math]::Max($peakHandles,$lastO.handles)
            $rows=@(Get-ChildItem -LiteralPath (Join-Path $store 'metrics') -Filter 'process_*.csv' -File|ForEach-Object {Import-Csv -LiteralPath $_.FullName})
            $sampleCount=$rows.Count
            if($sampleCount -lt 3 -or $sampleCount -gt 4){throw 'OBSERVER_SAMPLE_COUNT'}
            foreach($row in $rows){if($row.status -ne 'OK' -or [int]$row.pid -ne $g.Id){throw 'OBSERVER_SAMPLE_OWNERSHIP'}}
            if((Get-Content -LiteralPath (Join-Path $dir 'sampler.out') -Raw -ErrorAction SilentlyContinue) -match 'OBSERVER_SAMPLE_NOT_SAVED|OBSERVER_EXPORT_FAILED'){throw 'OBSERVER_SAMPLE_FAILURE'}
            # Separate manual export timing while sampling mutex remains owned.
            # Process CPU excludes any children; no journal or receipt fixture here.
            $exportClock=[Diagnostics.Stopwatch]::StartNew()
            $e=Start-Owned $ps ($argsCommon+@('-ExportNow')) (Join-Path $dir 'export')
            if(-not $e.WaitForExit(20000) -or $e.ExitCode -ne 0){throw 'OBSERVER_EXPORT'}
            $exportMs=$exportClock.ElapsedMilliseconds
            $exportCpu=[long][Math]::Round($e.TotalProcessorTime.Ticks/10000.0)
            if($o.HasExited -or $g.HasExited){throw 'OBSERVER_EXPORT_INTERFERENCE'}
            $zip=@(Get-ChildItem -LiteralPath (Join-Path $store 'reports') -Filter '*.zip' -File)
            if($zip.Count -ne 1){throw 'OBSERVER_EXPORT_COUNT'}
            $unpack=Join-Path $dir 'unpacked'
            Expand-Archive -LiteralPath $zip[0].FullName -DestinationPath $unpack
            $manifest=Get-Content -LiteralPath (Join-Path $unpack 'manifest.json') -Raw|ConvertFrom-Json
            if($manifest.valid_process_samples -lt $sampleCount -or $manifest.actual_samples -ne $manifest.valid_process_samples -or
               $manifest.automatic_upload -ne $false){throw 'OBSERVER_EXPORT_COVERAGE'}
        }elseif(Test-Path -LiteralPath $store){throw 'OBSERVER_OFF_STORAGE'}
        $mode=if($enabled){'on'}else{'off'}
        $gstCpu=[long][Math]::Round(($last.cpu-$first.cpu)/10000.0)
        Write-Host ('C545D_OBSERVER_ABBA_ARM,arm='+$name+',mode='+$mode+',elapsed_ms='+$elapsed+
            ',samples='+$sampleCount+',gst_cpu_ms='+$gstCpu+',gst_private_first_b='+$first.private+',gst_private_last_b='+$last.private+
            ',gst_handles_first='+$first.handles+',gst_handles_last='+$last.handles+
            ',observer_cpu_ms='+$observerCpu+',observer_private_first_b='+$observerPrivateFirst+',observer_private_last_b='+$observerPrivateLast+
            ',observer_private_sample_peak_b='+$peakPrivate+',observer_handles_first='+$observerHandlesFirst+
            ',observer_handles_last='+$observerHandlesLast+',observer_handles_sample_peak='+$peakHandles+
            ',manual_export_wall_ms='+$exportMs+',manual_export_process_cpu_ms='+$exportCpu+',real_camera=0')
    }finally{Close-Owned $e;Close-Owned $o;Close-Owned $g}
}
try{
    $env:PATH=(Join-Path $SdkRoot 'bin')+';'+$old['PATH']
    $env:GST_PLUGIN_PATH='';$env:GST_PLUGIN_PATH_1_0=''
    $env:GST_PLUGIN_SYSTEM_PATH='';$env:GST_PLUGIN_SYSTEM_PATH_1_0=Join-Path $SdkRoot 'lib\gstreamer-1.0'
    $env:GST_REGISTRY=Join-Path $root 'registry.bin'
    # Warm the common plugin registry outside the measured arms.
    # WinPS 5.1 turns redirected native stderr into NativeCommandError
    # even when a plugin scan warning is unrelated to the required graph.
    # Capture both streams privately; qualify actual process exit, not silence.
    $warm=$null
    try{
        $warm=Start-Owned $gst @('-q','videotestsrc','num-buffers=1','!','fakesink') (Join-Path $root 'warmup')
        if(-not $warm.WaitForExit(20000) -or $warm.ExitCode -ne 0){throw 'GST_WARMUP'}
        $warn=[int]((Get-Content -LiteralPath (Join-Path $root 'warmup.err') -Raw) -match 'gstpython\.dll')
        Write-Host "C545D_OBSERVER_WARMUP_PASS,exit=0,python_plugin_warning=$warn,real_camera=0"
    }finally{Close-Owned $warm}
    foreach($name in @('a1','b1','b2','a2')){Run-Arm $name ($name.StartsWith('b'))}
    Write-Host 'C545D_OBSERVER_ABBA_PASS,arms=4,packaged_source=1,same_runner=1,sampling_interval_s=10,synthetic_gst=1,manual_export=1,short_fixture_only=1,real_camera=0,install_approved=0'
}finally{
    foreach($k in $old.Keys){[Environment]::SetEnvironmentVariable($k,$old[$k],'Process')}
    # Disposable runner only; no exported raw logs or sample CSV.
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
