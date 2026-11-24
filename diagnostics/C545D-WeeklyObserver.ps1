# C545D diagnostic companion v0.4.0: Windows 10 / PowerShell 5.1.
# Separate, read-only and low-frequency. No recorder injection or restart.
[CmdletBinding()]
param(
  [ValidateRange(10,600)][int]$IntervalSeconds=60,
  [string]$RootDirectory=(Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\WeeklyObserver'),
  [string]$RecorderLogDirectory=(Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Logs'),
  [string]$MetadataJournalRoot=(Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\MetadataV04\journal'),
  [string]$WriterReceiptRoot=(Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\MetadataV04\receipts'),
  [switch]$SelfTest,
  [switch]$Once,
  [switch]$ExportNow
)
$ErrorActionPreference='Stop'
$culture=[Globalization.CultureInfo]::InvariantCulture
$utf8=New-Object Text.UTF8Encoding($false)
$version='0.4.0'
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
# Passive source: existing finalized-file renamer's timestamped log ONLY.
# We never enumerate, open, probe or rename any video file from this observer.
# Extract allowlisted event names and integer counts; discard all log payload.
function Read-NamerEvents([string]$directory,[datetime]$begin,[datetime]$end){
 $events=New-Object 'System.Collections.Generic.List[object]'
 $result=[pscustomobject]@{
   status='not_found';events=$events
   renamed=0;deferred=0;watcher_losses=0;watcher_errors=0;scan_lines=0
 }
 $path=Join-Path $directory 'Filename_Rename.log'
 if(-not(Test-Path -LiteralPath $path -PathType Leaf)){return $result}
 $stream=$null;$reader=$null
 try{
   $file=Get-Item -LiteralPath $path -Force -ErrorAction Stop
   if($file.Length -gt 8MB){$result.status='source_too_large';return $result}
   if(($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){
     $result.status='source_reparse_rejected';return $result
   }
   $stream=[IO.File]::Open($file.FullName,[IO.FileMode]::Open,
     [IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
   $reader=New-Object IO.StreamReader($stream,[Text.Encoding]::UTF8,$true)
   $result.status='complete'
   while(($line=$reader.ReadLine()) -ne $null){
     $result.scan_lines++
     if($result.scan_lines -gt 100000){
       $result.status='scan_limit';break
     }
     if($line.Length -gt 8192){continue}
     $m=[regex]::Match($line,
       '^(?<time>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)  (?<event>Renamed \(closed\): |Rename deferred \(|WARNING: FileSystemWatcher lost events \(|Watcher shutdown grace expired|ERROR event watcher:)')
     if(-not $m.Success){continue}
     try{
       $stamp=[datetime]::ParseExact($m.Groups['time'].Value,
         'yyyy-MM-dd HH:mm:ss',$culture,
         [Globalization.DateTimeStyles]::AssumeLocal).ToUniversalTime()
     }catch{continue}
     if($stamp -lt $begin -or $stamp -ge $end){continue}
     $kind='';$number=1
     $label=$m.Groups['event'].Value
     if($label -eq 'Renamed (closed): '){
       $kind='MP4_RENAME_AFTER_CLOSED';$result.renamed++
     }elseif($label -eq 'Rename deferred ('){
       $kind='MP4_RENAME_DEFERRED';$result.deferred++
     }elseif($label -eq 'WARNING: FileSystemWatcher lost events ('){
       $n=[regex]::Match($line.Substring($m.Length),'^\d{1,6}\)')
       if(-not $n.Success){continue}
       $number=[int]($n.Value.TrimEnd(')'))
       $kind='MP4_WATCHER_LOST_EVENTS';$result.watcher_losses+=$number
     }elseif($label -eq 'Watcher shutdown grace expired'){
       $kind='MP4_WATCHER_SHUTDOWN_TIMEOUT';$result.watcher_errors++
     }elseif($label -eq 'ERROR event watcher:'){
       $kind='MP4_WATCHER_ERROR';$result.watcher_errors++
     }else{continue}
     if($events.Count -ge 20000){$result.status='event_limit';break}
     $events.Add([pscustomobject][ordered]@{
       utc_time=UtcText $stamp;event=$kind;count=$number
     })
   }
   if($result.status -ne 'complete'){
     $events.Clear()
     $result.renamed=0;$result.deferred=0
     $result.watcher_losses=0;$result.watcher_errors=0
   }
 }catch{
   $result.status='source_unreadable'
   $events.Clear()
   $result.renamed=0;$result.deferred=0
   $result.watcher_losses=0;$result.watcher_errors=0
 }finally{
   if($reader){$reader.Dispose()}
   elseif($stream){$stream.Dispose()}
 }
 return $result
}
# Existing RecordGUIWorker.ps1 transcribes stdout into Recording_*.txt.
# Every line is NOT timestamped: ONLY source-file LastWriteTimeUtc is used to
# select a recording SESSION, never to timestamp an exit/reconnect/EOS event.
# A log which did not reach "Windows PowerShell transcript end" cannot prove
# a fully completed session: it remains incomplete_or_active.
# This parser returns only fixed numeric/count/enum fields; no raw lines,
# PIDs, filenames, local paths, RTSP addresses or exception messages.
function Read-WorkerSessions([string]$directory,[datetime]$begin,[datetime]$end){
 $sessions=New-Object 'System.Collections.Generic.List[object]'
 $result=[pscustomobject]@{
   status='not_found'; sessions=$sessions; files_seen=0
   completed_sessions=0; incomplete_sessions=0
   eos_reported=0; policy_reconnect=0; unexpected_exit=0
   nonzero_exit=0
 }
 if(-not(Test-Path -LiteralPath $directory -PathType Container)){
   return $result
 }
 try{
   $files=@(Get-ChildItem -LiteralPath $directory -Filter 'Recording_*.txt' -File -ErrorAction Stop)
 }catch{$result.status='source_enumeration_error';return $result}
 if($files.Count -gt 100){$result.status='source_count_limit';return $result}
 $result.status='complete'
 foreach($file in $files){
   if($file.Name -cnotmatch '^Recording_\d{8}_\d{6}_\d{1,10}\.txt$'){continue}
   # Snapshot selection uses file mtime only; session events have no clock.
   if($file.LastWriteTimeUtc -lt $begin -or $file.LastWriteTimeUtc -ge $end){continue}
   if($sessions.Count -ge 80){$result.status='session_count_limit';break}
   $result.files_seen++
   $state='incomplete_or_active'
   $launch=0;$returned=0;$policyReconnect=0;$unexpected=0;$nonzero=0
   $eos=0;$stopMarkerRc0=$false;$stopPolicy=$false;$transcriptEnd=$false
   $scan=0;$stream=$null;$reader=$null
   if($file.Length -gt 8MB){$state='source_too_large'}
   elseif(($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){
     $state='source_reparse_rejected'
   }else{
     try{
       $stream=[IO.File]::Open($file.FullName,[IO.FileMode]::Open,
         [IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
       $reader=New-Object IO.StreamReader($stream,[Text.Encoding]::UTF8,$true)
       while(($line=$reader.ReadLine()) -ne $null){
         $scan++
         if($scan -gt 100000){$state='line_limit';break}
         if($line.Length -gt 8192){continue}
         # Source markers defined in Record.ps1, not arbitrary stderr text.
         if($line -cmatch '^GStreamer launching \(EOS enabled\); attempt=([1-9]\d{0,5})\s*$'){
           $launch++;$stopMarkerRc0=$false;$stopPolicy=$false
         }elseif($line -cmatch '^GStreamer returned; exitCode=(-?\d{1,10}); stopMarker=(True|False); consoleCtrlCEvents=(\d{1,8})\s*$'){
           $value=0
           if(-not [int]::TryParse($matches[1],[ref]$value)){
             $state='invalid_exit_code';break
           }
           $returned++;$stopMarkerRc0=($value -eq 0 -and $matches[2] -ceq 'True')
           $stopPolicy=$false
           if($value -ne 0){$nonzero++}
           if($matches[2] -ceq 'False'){$unexpected++}
         }elseif($line -cmatch '^Recorder exit policy: (stop|reconnect)\s*$'){
           if($matches[1] -ceq 'reconnect'){$policyReconnect++}
           $stopPolicy=$matches[1] -ceq 'stop'
         }elseif($line -ceq 'Recording stopped by GUI; GStreamer EOS completed.'){
           # Require BOTH an explicitly authorized stop with rc0, and
           # a source policy=stop in the same session. Never count alone.
           if($stopMarkerRc0 -and $stopPolicy){
             $eos++;$stopMarkerRc0=$false;$stopPolicy=$false
           }
         }elseif($line -ceq 'Windows PowerShell transcript end'){
           $transcriptEnd=$true
         }
       }
       if($state -eq 'incomplete_or_active' -and $transcriptEnd){
         $state='complete'
       }
     }catch{$state='source_unreadable'}
     finally{
       if($reader){$reader.Dispose()}
       elseif($stream){$stream.Dispose()}
     }
   }
   # A partial or failed source is NOT proof of any outcome; hide counters
   # rather than silently classify the absent events as zero.
   if($state -ne 'complete'){
     $launch=0;$returned=0;$policyReconnect=0
     $unexpected=0;$nonzero=0;$eos=0
     $result.incomplete_sessions++
   }else{
     $result.completed_sessions++
     $result.eos_reported+=$eos
     $result.policy_reconnect+=$policyReconnect
     $result.unexpected_exit+=$unexpected
     $result.nonzero_exit+=$nonzero
   }
   $sessions.Add([pscustomobject][ordered]@{
     source_last_write_utc=UtcText $file.LastWriteTimeUtc
     session_index=$sessions.Count+1
     source_status=$state
     launch_count=$launch
     gst_return_count=$returned
     authorized_eos_reported_count=$eos
     reconnect_policy_count=$policyReconnect
     exit_without_stop_marker_count=$unexpected
     nonzero_exit_count=$nonzero
     event_time_resolution='session_only'
   })
 }
 # A directory with no qualifying (session,mtime) file is not evidence of
 # error-free operation. An unfinished transcript means partial coverage.
 if($result.status -eq 'complete'){
   if($result.files_seen -eq 0){$result.status='no_sessions_in_window'}
   elseif($result.incomplete_sessions -gt 0){$result.status='partial_or_active'}
 }
 return $result
}

# Load exactly once, only when report sources exist. No sampling-loop compilation.
$script:metadataReportLoadAttempted=$false
function Initialize-MetadataReportTypes {
    if(-not $script:metadataReportLoadAttempted){
        $script:metadataReportLoadAttempted=$true
        try{
            Add-Type -Path @((Join-Path $PSScriptRoot 'C545DMetadataJournalV04.cs'),(Join-Path $PSScriptRoot 'C545DMetadataWriterV04.cs')) -ErrorAction Stop
        }catch{}
    }
    return [bool](('C545DMetadataJournalV04' -as [type]) -and ('C545DWriterReceipts' -as [type]))
}

# Read-only v0.4 report adapter.
# Source is typed bounded journal; never copy raw journal bytes into ZIP.
function Read-C545DMetadataReport([string]$journal,[datetime]$begin,[datetime]$end,$namer){
    $rows=New-Object 'System.Collections.Generic.List[object]'
    $result=[pscustomobject]@{
        status='not_found';rows=$rows;invalid_slots=0;busy_slots=0;saturated_slots=0;recovered_slots=0
        matches=0;mismatches=0;unknown=0;count_difference='not_classified'
        coverage='not_proven'
    }
    if($journal -and (Test-Path -LiteralPath $journal -PathType Container)){
        try{
            if(-not (Initialize-MetadataReportTypes)){throw 'METADATA_READER_UNAVAILABLE'}
            $snap=[C545DMetadataJournalV04]::ReadWindow($journal,$begin.ToUniversalTime(),$end.ToUniversalTime())
            $result.status=$snap.Status
            $result.invalid_slots=$snap.InvalidSlots
            $result.busy_slots=$snap.BusySlots
            $result.saturated_slots=$snap.SaturatedSlots
            $result.recovered_slots=$snap.RecoveredSlots
            foreach($r in $snap.Rows){
                $rows.Add([pscustomobject][ordered]@{
                    publication_utc=UtcText $r.Utc
                    metadata_status=$r.Status;duration_ms=$r.DurationMs
                    video_tracks=$r.VideoTracks;audio_tracks=$r.AudioTracks
                    width=$r.Width;height=$r.Height;fps_num=$r.FpsNum;fps_den=$r.FpsDen
                    sample_rate=$r.SampleRate;channels=$r.Channels
                    video_h264=$r.H264;audio_aac=$r.Aac
                })
                if($r.Status -eq 'profile_match_metadata_only'){$result.matches++}
                elseif($r.Status -eq 'profile_mismatch'){$result.mismatches++}
                else{$result.unknown++}
            }
            # Aggregate only. Count agreement is not per-event identity or proof
            # of complete coverage, especially near the reporting boundary.
            if($namer.status -eq 'complete' -and $snap.Status -in @('coverage_unverified','no_events_coverage_unverified')){
                $result.count_difference=[int]$namer.renamed-$rows.Count
            }
        }catch{
            $result.status='reader_unavailable';$rows.Clear()
            $result.matches=0;$result.mismatches=0;$result.unknown=0
            $result.count_difference='not_classified'
        }
    }
    return $result
}
function Write-C545DMetadataCsv($metadata,[string]$path){
    $fields=@('publication_utc','metadata_status','duration_ms','video_tracks','audio_tracks',
      'width','height','fps_num','fps_den','sample_rate','channels','video_h264','audio_aac')
    if($metadata.rows.Count -gt 0){
        $metadata.rows | Select-Object -Property $fields |
          Export-Csv -LiteralPath $path -NoTypeInformation -Encoding UTF8
    }else{
        [IO.File]::WriteAllText($path,($fields -join ',')+[Environment]::NewLine,$utf8)
    }
}

# Whole-run counters only, never interpreted as exact totals inside report dates.
function Read-C545DWriterReport([string]$root,[datetime]$begin,[datetime]$end){
    $rows=New-Object 'System.Collections.Generic.List[object]'
    $r=[pscustomobject]@{status='not_found';rows=$rows;completed=0;unfinished=0;invalid=0;busy=0}
    if(-not $root -or -not(Test-Path -LiteralPath $root -PathType Container)){return $r}
    try{
        if(-not (Initialize-MetadataReportTypes)){throw 'METADATA_READER_UNAVAILABLE'}
        $s=[C545DWriterReceipts]::ReadWindow($root,$begin.ToUniversalTime(),$end.ToUniversalTime())
        $r.status=$s.Status;$r.completed=$s.CompletedRuns;$r.unfinished=$s.UnfinishedRuns
        $r.invalid=$s.InvalidSlots;$r.busy=$s.BusySlots
        foreach($e in $s.Rows){
            $state='unfinished_or_active';$endText='';$accepted='unknown';$rejected='unknown'
            $saved='unknown';$failed='unknown';$recovered='unknown'
            if($e.Final){
                $state='final_counters_saved';$endText=UtcText $e.EndUtc
                $accepted=$e.Accepted;$rejected=$e.Rejected;$saved=$e.Saved;$failed=$e.Failed;$recovered=$e.Recovered
            }
            $rows.Add([pscustomobject][ordered]@{
                start_utc=UtcText $e.StartUtc;end_utc=$endText;state=$state
                accepted=$accepted;rejected=$rejected;saved=$saved;failed=$failed;recovered=$recovered
                counter_scope='whole_run_not_report_window'
            })
        }
    }catch{
        $r.status='reader_unavailable';$rows.Clear()
        $r.completed=0;$r.unfinished=0;$r.invalid=0;$r.busy=0
    }
    return $r
}
function Write-C545DWriterCsv($report,[string]$path){
    $fields=@('start_utc','end_utc','state','accepted','rejected','saved','failed','recovered','counter_scope')
    if($report.rows.Count -gt 0){
        $report.rows | Select-Object -Property $fields | Export-Csv -LiteralPath $path -NoTypeInformation -Encoding UTF8
    }else{
        [IO.File]::WriteAllText($path,($fields -join ',')+[Environment]::NewLine,$utf8)
    }
}

# Current on-disk package only. Never attribute historical samples to this snapshot.
# Fixed paths, no raw manifest or private path copied, no executable launched.
function Test-IdentityLocalPath([string]$path){
    if($path -notmatch '^[A-Za-z]:\\'){return $false}
    $d=New-Object IO.DirectoryInfo([IO.Path]::GetFullPath($path))
    if((New-Object IO.DriveInfo($d.Root.FullName)).DriveType -ne [IO.DriveType]::Fixed){return $false}
    while($d){
        if(-not $d.Exists -or ($d.Attributes -band [IO.FileAttributes]::ReparsePoint)){return $false}
        $d=$d.Parent
    }
    return $true
}
function Read-PackageIdentity {
    $r=[ordered]@{status='not_found';source_commit='unknown';manifest_observer_version='unknown';
        checked_files=0;matched_files=0;scope='export_time_disk_snapshot_only';
        report_window_attribution='not_proven';loaded_runtime_identity='not_collected';
        authenticity='not_proven';observed_utc=UtcText ([datetime]::UtcNow)}
    try{
        $package=Split-Path -Parent $PSScriptRoot
        $manifestPath=Join-Path $package 'BUILD_IDENTITY.json'
        if(-not(Test-Path -LiteralPath $manifestPath -PathType Leaf)){return $r}
        if(-not(Test-IdentityLocalPath $package)){$r.status='path_rejected';return $r}
        $item=Get-Item -LiteralPath $manifestPath
        if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 16384){
            $r.status='manifest_rejected';return $r
        }
        $stream=$null
        try{
            $stream=[IO.File]::Open($manifestPath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
            if($stream.Length -le 0 -or $stream.Length -gt 16384){throw 'IDENTITY_SIZE'}
            $reader=New-Object IO.StreamReader($stream)
            try{$raw=$reader.ReadToEnd()}finally{$reader.Dispose()}
        }finally{if($stream){$stream.Dispose()}}
        $m=ConvertFrom-Json -InputObject $raw -ErrorAction Stop
        $expected=@('C545D_Recorder.exe','Record.ps1','RecordGUIWorker.ps1','SegmentNamer.ps1','SegmentNamerWorker.ps1',
          'diagnostics/C545D-WeeklyObserver.ps1','plugins/gstc545dsei.dll','diagnostics/C545DClosedProbeV04.cs',
          'diagnostics/C545DMetadataJournalV04.cs','diagnostics/C545DMetadataWriterV04.cs',
          'diagnostics/C545D-MetadataClassifierV04.ps1','diagnostics/C545D-MetadataIntegrationV04.ps1')
        if($m.schema_version -ne 1 -or $m.source_commit -isnot [string] -or
           $m.source_commit -cnotmatch '\A[0-9a-f]{40}\z' -or $m.observer_version -cne '0.4.0' -or
           $m.metadata_candidate_version -cne '0.4.0' -or $m.metadata_default_enabled -ne 0 -or
           $m.host_runtime_verified -ne 0 -or @($m.files.PSObject.Properties).Count -ne $expected.Count){
            $r.status='manifest_rejected';return $r
        }
        foreach($name in $expected){
            $p=$m.files.PSObject.Properties[$name]
            if($null -eq $p -or $p.Value -isnot [string] -or $p.Value -notmatch '\A[0-9A-Fa-f]{64}\z'){
                $r.status='manifest_rejected';return $r
            }
        }
        $total=0L
        foreach($name in $expected){
            $file=Join-Path $package $name
            if(-not(Test-IdentityLocalPath (Split-Path -Parent $file))){
                $r.status='file_unavailable';return $r
            }
            $item=Get-Item -LiteralPath $file -ErrorAction Stop
            if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
               $item.Length -gt 67108864){$r.status='file_rejected';return $r}
            $total+=$item.Length
            if($total -gt 134217728){$r.status='size_limit';return $r}
            $beforeLength=$item.Length;$beforeWrite=$item.LastWriteTimeUtc
            $actual=(Get-FileHash -LiteralPath $file -Algorithm SHA256 -ErrorAction Stop).Hash
            $after=Get-Item -LiteralPath $file -ErrorAction Stop
            if($after.Length -ne $beforeLength -or $after.LastWriteTimeUtc -ne $beforeWrite){
                $r.status='file_changed';return $r
            }
            $r.checked_files++
            if($actual -ieq $m.files.PSObject.Properties[$name].Value){$r.matched_files++}
        }
        if($r.matched_files -ne $expected.Count){$r.status='hash_mismatch';return $r}
        $r.status='manifest_hashes_match'
        $r.source_commit=$m.source_commit
        $r.manifest_observer_version='0.4.0'
    }catch{$r.status='reader_unavailable'}
    return $r
}

function New-SafeBundle([string]$root,[datetime]$begin,[datetime]$end,[string]$reason){
 if($end -le $begin -or ($end-$begin).TotalDays -gt 31){throw 'REPORT_WINDOW_INVALID'}
 $rows=Read-ValidRows $root $begin $end
 $media=Read-NamerEvents $RecorderLogDirectory $begin $end
 $worker=Read-WorkerSessions $RecorderLogDirectory $begin $end
 $writerReport=Read-C545DWriterReport $WriterReceiptRoot $begin $end
 $metadata=Read-C545DMetadataReport $MetadataJournalRoot $begin $end $media
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
     package_identity=(Read-PackageIdentity)
     writer_receipt_source_status=$writerReport.status
     writer_completed_runs=$writerReport.completed
     writer_unfinished_or_active_runs=$writerReport.unfinished
     writer_invalid_slots=$writerReport.invalid
     writer_busy_slots=$writerReport.busy
     writer_event_coverage='not_proven'
     writer_counter_scope='whole_run_not_report_window'
     metadata_journal_source_status=$metadata.status
     metadata_journal_invalid_slots=$metadata.invalid_slots
     metadata_journal_busy_slots=$metadata.busy_slots
     metadata_journal_saturated_slots=$metadata.saturated_slots
     metadata_journal_recovered_slots=$metadata.recovered_slots
     metadata_event_count=$metadata.rows.Count
     metadata_profile_match_count=$metadata.matches
     metadata_profile_mismatch_count=$metadata.mismatches
     metadata_unknown_count=$metadata.unknown
     metadata_rename_count_difference=$metadata.count_difference
     metadata_event_coverage='not_proven'
     metadata_time_semantics='publication_utc_not_exact_rename_time'
     camera_composition='not_collected';av_sync='not_collected';full_media_decode='not_collected'
     utc_from=UtcText $begin;utc_until=UtcText $end;mode=$reason
     expected_sample_interval_seconds=60
     actual_samples=$samples.Count;valid_process_samples=$okay
     unavailable_process_samples=$samples.Count-$okay
     missing_intervals='not_classified'
     recording_integrity='closed_rename_events_only_not_media_integrity'
     namer_event_source_status=$media.status
     renamed_closed_mp4_count=$media.renamed
     video_stream_count='not_collected'
     aac_audio_integrity='not_collected'
     mp4_duration='not_collected'
     eos_confirmation='recorder_log_reported_only_not_mp4_proven'
     recorder_session_event_source_status=$worker.status
     recorder_completed_transcripts=$worker.completed_sessions
     recorder_incomplete_transcripts=$worker.incomplete_sessions
     recorder_reported_authorized_eos_count=$worker.eos_reported
     precise_recorder_event_timestamps='not_collected'
     rtsp_reconnects='not_collected'
     gstreamer_heap_attribution='not_collected'
     heavy_etw='disabled';automatic_upload=$false
   }
   $summary=[ordered]@{
     actual_samples=$samples.Count;valid_samples=$okay
     not_running=@($samples|Where-Object status -eq 'NOT_RUNNING').Count
     ambiguous_gstreamer_process=@($samples|Where-Object status -eq 'MULTIPLE_PROCESSES').Count
     memory_leak_proven=$false
     closed_mp4_rename_events=$media.renamed
     rename_deferred_events=$media.deferred
     watcher_lost_event_count=$media.watcher_losses
     watcher_error_count=$media.watcher_errors
     namer_source_status=$media.status
     worker_session_log_source_status=$worker.status
     worker_session_reported_eos_count=$worker.eos_reported
     worker_session_reconnect_policy_count=$worker.policy_reconnect
     worker_session_unexpected_exit_count=$worker.unexpected_exit
     worker_session_nonzero_exit_count=$worker.nonzero_exit
     worker_session_incomplete_count=$worker.incomplete_sessions
     next_instrumentation_gap='actual_mp4_AV_duration_and_precise_EOS_times_not_proven_by_session_log'
   }
   $writerFile=Join-Path $work 'diagnostic_writer_runs.csv'
   Write-C545DWriterCsv $writerReport $writerFile
   $metadataFile=Join-Path $work 'mp4_metadata.csv'
   Write-C545DMetadataCsv $metadata $metadataFile
   $summary['metadata_event_count']=$metadata.rows.Count
   $summary['metadata_coverage']='not_proven'
   $metric=Join-Path $work 'process_metrics.csv'
   if($samples.Count){
     $samples | Select-Object -Property $columns | Export-Csv -LiteralPath $metric -NoTypeInformation -Encoding UTF8
   }else{
     [IO.File]::WriteAllText($metric,($columns -join ',')+[Environment]::NewLine,$utf8)
   }
   $mediaFile=Join-Path $work 'recording_events.csv'
   # Windows PowerShell 5.1 may throw a dynamic binder ArgumentException
   # when wrapping a generic List property inside @(...). Enumerate directly.
   if($media.events.Count -gt 0) {
     $media.events | Select-Object utc_time,event,count |
       Export-Csv -LiteralPath $mediaFile -NoTypeInformation -Encoding UTF8
   }else{
     [IO.File]::WriteAllText($mediaFile,'utc_time,event,count'+[Environment]::NewLine,$utf8)
   }
   $sessionFile=Join-Path $work 'recorder_sessions.csv'
   if($worker.sessions.Count -gt 0){
     $worker.sessions | Select-Object source_last_write_utc,session_index,
       source_status,launch_count,gst_return_count,authorized_eos_reported_count,
       reconnect_policy_count,exit_without_stop_marker_count,nonzero_exit_count,
       event_time_resolution |
       Export-Csv -LiteralPath $sessionFile -NoTypeInformation -Encoding UTF8
   }else{
     $sessionHeader=@('source_last_write_utc','session_index','source_status',
       'launch_count','gst_return_count','authorized_eos_reported_count',
       'reconnect_policy_count','exit_without_stop_marker_count',
       'nonzero_exit_count','event_time_resolution')
     [IO.File]::WriteAllText($sessionFile,
       ($sessionHeader -join ',')+[Environment]::NewLine,$utf8)
   }
   [IO.File]::WriteAllText((Join-Path $work 'manifest.json'),
      (ConvertTo-Json $manifest -Depth 4 -Compress),$utf8)
   [IO.File]::WriteAllText((Join-Path $work 'summary.json'),
      (ConvertTo-Json $summary -Depth 4 -Compress),$utf8)
   Compress-Archive -LiteralPath @($metric,$mediaFile,$sessionFile,$metadataFile,$writerFile,(Join-Path $work 'manifest.json'),
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
   # Synthetic preexisting namer log contains private file/RTSP text;
   # only allowlisted event type, UTC time and count may appear in the ZIP.
   $logFixture=Join-Path $root 'fake_namer_logs'
   New-Item -ItemType Directory -Path $logFixture -Force | Out-Null
   $script:RecorderLogDirectory=$logFixture
   $script:MetadataJournalRoot=Join-Path $root 'missing_journal'
   $script:WriterReceiptRoot=Join-Path $root 'missing_receipts'
   $t=$now.ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss',$culture)
   [IO.File]::WriteAllLines((Join-Path $logFixture 'Filename_Rename.log'),@(
     ($t+'  Renamed (closed): PRIVATE_SECRET_923.mp4 -> rtsp://secret@host/stream1'),
     ($t+'  WARNING: FileSystemWatcher lost events (3). Run a private script.'),
     ($t+'  Rename deferred (secret): C:\Users\PRIVATE_SECRET_923')
   ),$utf8)
   $stem='Recording_'+$now.ToLocalTime().ToString('yyyyMMdd_HHmmss',$culture)+'_'
   $completed=@(
     'GStreamer launching (EOS enabled); attempt=1',
     'RTSP_PASSWORD_SECRET_992 from a process output line',
     'GStreamer returned; exitCode=1; stopMarker=False; consoleCtrlCEvents=0',
     'Recorder exit policy: reconnect',
     'GStreamer launching (EOS enabled); attempt=2',
     'GStreamer returned; exitCode=0; stopMarker=True; consoleCtrlCEvents=1',
     'Recorder exit policy: stop',
     'Recording stopped by GUI; GStreamer EOS completed.',
     'Windows PowerShell transcript end'
   )
   [IO.File]::WriteAllLines((Join-Path $logFixture ($stem+'991.txt')),$completed,$utf8)
   # A fake success marker alone, even inside an ended transcript, must
   # NOT count as EOS without the paired authorized rc0+stop policy.
   [IO.File]::WriteAllLines((Join-Path $logFixture ($stem+'992.txt')),@(
     'RTSP_PASSWORD_SECRET_992 in original output',
     'Recording stopped by GUI; GStreamer EOS completed.',
     'Windows PowerShell transcript end'
   ),$utf8)
   # A still-running/incomplete transcript is not negative proof.
   [IO.File]::WriteAllLines((Join-Path $logFixture ($stem+'993.txt')),@(
     'GStreamer returned; exitCode=0; stopMarker=True; consoleCtrlCEvents=1',
     'Recorder exit policy: stop',
     'Recording stopped by GUI; GStreamer EOS completed.'
   ),$utf8)
   $zip=New-SafeBundle $root $now.AddHours(-1) $now.AddHours(1) 'selftest'
   $unpacked=Join-Path $root 'unpacked'
   Expand-Archive -LiteralPath $zip -DestinationPath $unpacked
   $meta=Get-Content (Join-Path $unpacked 'manifest.json') -Raw | ConvertFrom-Json
   if(@(Get-ChildItem $unpacked -File).Count -ne 7 -or
      $meta.metadata_journal_source_status -ne 'not_found' -or
      $meta.writer_receipt_source_status -ne 'not_found' -or
      $meta.metadata_event_coverage -ne 'not_proven' -or
      $meta.writer_event_coverage -ne 'not_proven'){throw 'SELFTEST_V04_MISSING_SOURCE'}
   $metric=Get-Content (Join-Path $unpacked 'process_metrics.csv') -Raw
   $mediaCsv=Get-Content (Join-Path $unpacked 'recording_events.csv') -Raw
   $workerCsv=Get-Content (Join-Path $unpacked 'recorder_sessions.csv') -Raw
   $workerRows=@(Import-Csv (Join-Path $unpacked 'recorder_sessions.csv'))
   $allReport=(@(Get-ChildItem $unpacked -File|ForEach-Object {
     [IO.File]::ReadAllText($_.FullName)
   }) -join [Environment]::NewLine)
   if($meta.diagnostics_version -ne $version -or $meta.heavy_etw -ne 'disabled' -or
      $meta.renamed_closed_mp4_count -ne 1 -or
      $mediaCsv -notmatch 'MP4_WATCHER_LOST_EVENTS' -or
      $mediaCsv -notmatch 'MP4_RENAME_DEFERRED' -or
      $allReport -match 'PRIVATE_SECRET_923|RTSP_PASSWORD_SECRET_992|rtsp://|C:\\Users\\' -or
      $meta.recorder_completed_transcripts -ne 2 -or
      $meta.recorder_incomplete_transcripts -ne 1 -or
      $meta.recorder_reported_authorized_eos_count -ne 1 -or
      $meta.recorder_session_event_source_status -ne 'partial_or_active' -or
      $workerRows.Count -ne 3 -or
      @($workerRows|Where-Object source_status -eq 'incomplete_or_active').Count -ne 1 -or
      @($workerRows|Where-Object authorized_eos_reported_count -eq '1').Count -ne 1 -or
      $workerCsv -notmatch 'session_only' -or
      $metric -notmatch 'private_bytes'){
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
   Write-Output 'C545D_WEEKLY_OBSERVER_SELFTEST_PASS,zip=1,windows51=1,schema=1,negative_redaction=1,namer_sanitized=1,closed_rename=1,watcher_loss=3,worker_eos_pair=1,reconnect=1,incomplete_session=1,72h_restart=1,72h_then_7d=1,empty_week_gap=1,recorder_untouched=1'
 }finally{
   Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
 }
}
if($SelfTest){
 try{Test-Observer}
 catch{
   Write-Host ('C545D_OBSERVER_SELFTEST_FAILURE,line='+
      $_.InvocationInfo.ScriptLineNumber+',type='+$_.Exception.GetType().Name)
   throw
 }
 exit 0
}
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
