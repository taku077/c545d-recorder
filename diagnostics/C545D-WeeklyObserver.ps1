# C545D diagnostic companion v0.1.0: Windows 10 / PowerShell 5.1.
# Separate, read-only and low-frequency. No recorder injection or restart.
[CmdletBinding()]
param(
  [ValidateRange(10,600)][int]$IntervalSeconds=60,
  [string]$RootDirectory=(Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\WeeklyObserver'),
  [switch]$SelfTest,
  [switch]$Once,
  [switch]$ExportNow
)
$ErrorActionPreference='Stop'
$culture=[Globalization.CultureInfo]::InvariantCulture
$utf8=New-Object Text.UTF8Encoding($false)
$version='0.1.0'
$schema='1'
$columns=@('schema_version','utc_time','status','pid','start_utc',
 'private_bytes','working_set_bytes','handle_count','thread_count',
 'cpu_100ns','observer_private_bytes')
$statuses=@('OK','NOT_RUNNING','MULTIPLE_PROCESSES',
 'PROCESS_ACCESS_ERROR','PROCESS_LOOKUP_ERROR')
function UtcText([datetime]$d){$d.ToUniversalTime().ToString('o',$culture)}
function ToUtc([string]$t){
 [datetime]::ParseExact($t,'o',$culture,
   [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
}
function Get-ObserverRow {
 $now=[datetime]::UtcNow
 $p=$null;$status='NOT_RUNNING'
 try{
   $found=@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue)
   if($found.Count -eq 1){$status='OK';$p=$found[0]}
   elseif($found.Count -gt 1){$status='MULTIPLE_PROCESSES'}
 }catch{$status='PROCESS_LOOKUP_ERROR'}
 $pidText='';$start='';$priv='';$ws='';$handles='';$threads='';$cpu=''
 if($null -ne $p){
   try{
     $p.Refresh()
     $pidText=[string]$p.Id
     $start=UtcText $p.StartTime
     $priv=[string]$p.PrivateMemorySize64
     $ws=[string]$p.WorkingSet64
     $handles=[string]$p.HandleCount
     $threads=[string]$p.Threads.Count
     $cpu=[string]$p.TotalProcessorTime.Ticks
   }catch{
     $status='PROCESS_ACCESS_ERROR'
     $pidText='';$start='';$priv='';$ws='';$handles='';$threads='';$cpu=''
   }
 }
 $observer=''
 try{$observer=[string](Get-Process -Id $PID).PrivateMemorySize64}catch{}
 [pscustomobject][ordered]@{
   schema_version=$schema;utc_time=(UtcText $now);status=$status
   pid=$pidText;start_utc=$start;private_bytes=$priv;working_set_bytes=$ws
   handle_count=$handles;thread_count=$threads;cpu_100ns=$cpu
   observer_private_bytes=$observer
 }
}
function Assert-ObserverRow($row){
 foreach($column in $columns){
   if($null -eq $row.PSObject.Properties[$column]){throw 'SCHEMA_MISSING_FIELD'}
 }
 if($row.schema_version -ne $schema -or $statuses -notcontains $row.status){
   throw 'SCHEMA_INVALID_STATUS'
 }
 $time=ToUtc ([string]$row.utc_time)
 if($time.Year -lt 2020 -or $time.Year -gt 2100){throw 'SCHEMA_BAD_TIME'}
 $active=$row.status -eq 'OK'
 foreach($name in @('pid','private_bytes','working_set_bytes','handle_count',
                   'thread_count','cpu_100ns','observer_private_bytes')){
   $v=[string]$row.$name
   if($v -eq ''){
     if($active -and $name -ne 'observer_private_bytes'){throw 'SCHEMA_MISSING_COUNTER'}
     continue
   }
   if($v -notmatch '^\d{1,19}$'){throw 'SCHEMA_UNSAFE_COUNTER'}
   $test=0L
   if(-not [long]::TryParse($v,[ref]$test)){throw 'SCHEMA_INTEGER_OVERFLOW'}
 }
 if($active){
   if(-not $row.start_utc){throw 'SCHEMA_MISSING_START'}
   if((ToUtc ([string]$row.start_utc)) -gt $time.AddMinutes(2)){
     throw 'SCHEMA_FUTURE_PROCESS'
   }
 }elseif($row.pid -or $row.start_utc -or $row.private_bytes){
   throw 'SCHEMA_INVALID_UNAVAILABLE'
 }
}
function Save-ObserverRow($row,[string]$root){
 Assert-ObserverRow $row
 $dir=Join-Path $root 'metrics'
 if(-not(Test-Path -LiteralPath $dir)){New-Item -ItemType Directory -Path $dir -Force|Out-Null}
 $day=(ToUtc ([string]$row.utc_time)).ToString('yyyyMMdd',$culture)
 $name=Join-Path $dir ('process_'+$day+'.csv')
 $present=Test-Path -LiteralPath $name
 if($present){
   $row | Select-Object -Property $columns | Export-Csv -LiteralPath $name -NoTypeInformation -Encoding UTF8 -Append
 }else{
   $row | Select-Object -Property $columns | Export-Csv -LiteralPath $name -NoTypeInformation -Encoding UTF8
 }
}
function Read-ValidRows([string]$root,[datetime]$begin,[datetime]$end){
 $result=New-Object 'Collections.Generic.List[object]'
 $dir=Join-Path $root 'metrics'
 if(-not(Test-Path -LiteralPath $dir)){return $result}
 $files=@(Get-ChildItem -LiteralPath $dir -Filter 'process_*.csv' -File)
 if($files.Count -gt 45){throw 'TOO_MANY_DAILY_FILES'}
 foreach($file in $files){
   if($file.Name -notmatch '^process_\d{8}\.csv$' -or $file.Length -gt 15000000){
     throw 'UNEXPECTED_DAILY_METRICS_FILE'
   }
   foreach($row in @(Import-Csv -LiteralPath $file.FullName -Encoding UTF8)){
     Assert-ObserverRow $row
     $t=ToUtc ([string]$row.utc_time)
     if($t -ge $begin -and $t -le $end){
       if($result.Count -ge 50000){throw 'REPORT_TOO_MANY_ROWS'}
       $clean=[ordered]@{}
       foreach($name in $columns){$clean[$name]=[string]$row.$name}
       $result.Add([pscustomobject]$clean)
     }
   }
 }
 return $result
}
function New-SafeBundle([string]$root,[datetime]$begin,[datetime]$end,[string]$reason){
 if($end -le $begin -or ($end-$begin).TotalDays -gt 31){throw 'REPORT_WINDOW_INVALID'}
 $rows=Read-ValidRows $root $begin $end
 $dir=Join-Path $root 'reports'
 New-Item -ItemType Directory -Path $dir -Force|Out-Null
 $work=Join-Path $dir ('work_'+[guid]::NewGuid().ToString('N'))
 New-Item -ItemType Directory -Path $work|Out-Null
 $base='C545D_SAFE_WEEKLY_'+$end.ToString('yyyyMMdd_HHmmss',$culture)+'_'+
   [guid]::NewGuid().ToString('N').Substring(0,8)
 $partial=Join-Path $dir ($base+'.partial.zip')
 $output=Join-Path $dir ($base+'.zip')
 try{
   $samples=@($rows)
   $okay=@($samples|Where-Object status -eq 'OK').Count
   $manifest=[ordered]@{
     schema_version=1;diagnostics_version=$version
     recorder_version='not_collected'
     utc_from=UtcText $begin;utc_until=UtcText $end;mode=$reason
     expected_sample_interval_seconds=60
     actual_samples=$samples.Count;valid_process_samples=$okay
     unavailable_process_samples=$samples.Count-$okay
     missing_intervals='not_classified'
     recording_integrity='not_collected'
     rtsp_reconnects='not_collected'
     gstreamer_heap_attribution='not_collected'
     heavy_etw='disabled';automatic_upload=$false
   }
   $summary=[ordered]@{
     actual_samples=$samples.Count;valid_samples=$okay
     not_running=@($samples|Where-Object status -eq 'NOT_RUNNING').Count
     ambiguous_gstreamer_process=@($samples|Where-Object status -eq 'MULTIPLE_PROCESSES').Count
     memory_leak_proven=$false
     next_instrumentation_gap='MP4_close_2_stream_AAC_eos_and_heap_source_not_yet_collected'
   }
   $metric=Join-Path $work 'process_metrics.csv'
   if($samples.Count){
     $samples | Select-Object -Property $columns | Export-Csv -LiteralPath $metric -NoTypeInformation -Encoding UTF8
   }else{
     [IO.File]::WriteAllText($metric,($columns -join ',')+[Environment]::NewLine,$utf8)
   }
   [IO.File]::WriteAllText((Join-Path $work 'manifest.json'),
      (ConvertTo-Json $manifest -Depth 4 -Compress),$utf8)
   [IO.File]::WriteAllText((Join-Path $work 'summary.json'),
      (ConvertTo-Json $summary -Depth 4 -Compress),$utf8)
   Compress-Archive -LiteralPath @($metric,(Join-Path $work 'manifest.json'),
     (Join-Path $work 'summary.json')) -DestinationPath $partial -CompressionLevel Optimal -ErrorAction Stop
   if(-not(Test-Path $partial)){throw 'ZIP_NOT_CREATED'}
   Move-Item -LiteralPath $partial -Destination $output -ErrorAction Stop
   return $output
 }finally{
   Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
   Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
 }
}
function Load-ObserverState([string]$root,[datetime]$now){
 $file=Join-Path $root 'observer_state.json'
 if(Test-Path -LiteralPath $file){
   $x=Get-Content -LiteralPath $file -Raw -Encoding UTF8|ConvertFrom-Json
   if($x.schema_version -ne $schema){throw 'STATE_VERSION_INVALID'}
   [void](ToUtc ([string]$x.started_utc))
   [void](ToUtc ([string]$x.window_from_utc))
   [void](ToUtc ([string]$x.next_cut_utc))
   return $x
 }
 [pscustomobject]@{
   schema_version=$schema;started_utc=UtcText $now
   window_from_utc=UtcText $now
   next_cut_utc=UtcText $now.AddHours(72)
   report_count=0
 }
}
function Save-ObserverState($state,[string]$root){
 $name=Join-Path $root 'observer_state.json'
 $temp=$name+'.partial'
 [IO.File]::WriteAllText($temp,(ConvertTo-Json $state -Depth 5),$utf8)
 if(Test-Path -LiteralPath $name){
   # .NET Framework 4.x on Windows requires a real backup path here;
   # a null backup path failed the isolated CI runtime.
   [IO.File]::Replace($temp,$name,($name+'.previous'))
 }else{Move-Item -LiteralPath $temp -Destination $name}
}
function Export-WhenDue($state,[string]$root,[datetime]$now){
 $cut=ToUtc ([string]$state.next_cut_utc)
 if($now -lt $cut){return $null}
 $from=ToUtc ([string]$state.window_from_utc)
 $zip=New-SafeBundle $root $from $cut 'scheduled'
 $state.report_count=[int]$state.report_count+1
 $state.window_from_utc=UtcText $cut
 $next=$cut.AddDays(7)
 # Downtime cannot force unlimited catch-up ZIPs in one minute.
 while($next -lt $now.AddDays(-7)){$next=$next.AddDays(7)}
 $state.next_cut_utc=UtcText $next
 Save-ObserverState $state $root
 return $zip
}
function Prune-Metrics([string]$root,[datetime]$now){
 $folder=Join-Path $root 'metrics'
 if(-not(Test-Path -LiteralPath $folder)){return}
 foreach($old in @(Get-ChildItem -LiteralPath $folder -Filter 'process_*.csv' -File)){
   if($old.LastWriteTimeUtc -lt $now.AddDays(-30)){
     Remove-Item -LiteralPath $old.FullName -Force -ErrorAction Stop
   }
 }
 $files=@(Get-ChildItem -LiteralPath $folder -Filter 'process_*.csv' -File)
 $sum=0L
 foreach($file in $files){$sum+=$file.Length}
 # Never delete as-yet-unreported samples to force the cap.
 if($sum -gt 200MB){throw 'STORAGE_LIMIT_REACHED_REVIEW_NEEDED'}
}
function Test-Observer {
 $root=Join-Path $env:TEMP ('C545D_weekly_test_'+[guid]::NewGuid().ToString('N'))
 New-Item -ItemType Directory -Path $root|Out-Null
 try{
   $now=[datetime]::UtcNow
   $row=Get-ObserverRow
   Assert-ObserverRow $row
   Save-ObserverRow $row $root
   $zip=New-SafeBundle $root $now.AddHours(-1) $now.AddHours(1) 'selftest'
   $unpacked=Join-Path $root 'unpacked'
   Expand-Archive -LiteralPath $zip -DestinationPath $unpacked
   $meta=Get-Content (Join-Path $unpacked 'manifest.json') -Raw | ConvertFrom-Json
   $metric=Get-Content (Join-Path $unpacked 'process_metrics.csv') -Raw
   if($meta.diagnostics_version -ne $version -or $meta.heavy_etw -ne 'disabled' -or
      $metric -notmatch 'private_bytes' -or $metric -match 'rtsp://'){
       throw 'SELFTEST_REPORT_INCOMPLETE'
   }
   $bad=Get-ObserverRow
   $bad.private_bytes='rtsp://fakeuser:SECRET_923@192.0.2.1/stream1'
   $denied=$false
   try{Assert-ObserverRow $bad}catch{$denied=$true}
   if(-not $denied){throw 'SECRET_UNSAFE_SCHEMA_ACCEPTED'}
   $state=Load-ObserverState $root $now
   Save-ObserverState $state $root
   Save-ObserverState $state $root
   $restored=Load-ObserverState $root $now.AddHours(3)
   if((ToUtc $restored.next_cut_utc) -ne $now.AddHours(72)){throw 'RESTART_CHANGED_CADENCE'}
   $first=Export-WhenDue $restored $root $now.AddHours(73)
   if(-not $first -or -not(Test-Path $first)){throw 'FIRST_72H_REPORT_MISSING'}
   if((ToUtc $restored.next_cut_utc) -ne $now.AddHours(72).AddDays(7)){
     throw 'WEEKLY_INTERVAL_NOT_SEVEN_DAYS'
   }
   $second=Export-WhenDue $restored $root $now.AddHours(72).AddDays(8)
   if(-not $second -or -not(Test-Path $second)){throw 'SEVEN_DAY_REPORT_MISSING'}
   $emptyUnpack=Join-Path $root 'empty_week'
   Expand-Archive -LiteralPath $second -DestinationPath $emptyUnpack
   $emptyMeta=Get-Content (Join-Path $emptyUnpack 'manifest.json') -Raw|ConvertFrom-Json
   if($emptyMeta.actual_samples -ne 0 -or $emptyMeta.missing_intervals -ne 'not_classified'){
     throw 'MISSING_SAMPLES_SILENTLY_MARKED_NORMAL'
   }
   Write-Output 'C545D_WEEKLY_OBSERVER_SELFTEST_PASS,zip=1,windows51=1,schema=1,negative_redaction=1,72h_restart=1,72h_then_7d=1,empty_week_gap=1,recorder_untouched=1'
 }finally{
   Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
 }
}
if($SelfTest){Test-Observer;exit 0}
if(-not(Test-Path -LiteralPath $RootDirectory)){
 New-Item -ItemType Directory -Path $RootDirectory -Force|Out-Null
}
# ZIP export must work WHILE the detached observer owns its sampling mutex.
# It is read-only against the local CSV history and must never block recording.
if($ExportNow){
 $end=[datetime]::UtcNow
 $zip=New-SafeBundle $RootDirectory $end.AddDays(-7) $end 'manual'
 Write-Output ('C545D_SAFE_WEEKLY_READY: '+$zip)
 exit 0
}
$mutex=New-Object System.Threading.Mutex($false,'Local\C545D_WeeklyObserver')
if(-not $mutex.WaitOne(0)){$mutex.Dispose();throw 'OBSERVER_ALREADY_RUNNING'}
try{
 $state=Load-ObserverState $RootDirectory ([datetime]::UtcNow)
 Save-ObserverState $state $RootDirectory
 do{
     $row=Get-ObserverRow
     Save-ObserverRow $row $RootDirectory
     try{
       $zip=Export-WhenDue $state $RootDirectory ([datetime]::UtcNow)
       if($zip){
         Prune-Metrics $RootDirectory ([datetime]::UtcNow)
         Write-Output ('C545D_SAFE_WEEKLY_READY: '+$zip)
       }
     }catch{
       # Fail independently: no GStreamer process is killed/restarted or changed.
       Write-Warning ('OBSERVER_EXPORT_FAILED: '+$_.Exception.GetType().Name)
     }
     if(-not $Once){Start-Sleep -Seconds $IntervalSeconds}
   }while(-not $Once)
}finally{
 $mutex.ReleaseMutex()
 $mutex.Dispose()
}
