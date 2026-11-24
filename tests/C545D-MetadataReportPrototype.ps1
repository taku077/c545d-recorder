# CI-only adapter, loaded into an isolated copy of the actual weekly observer.
# Source is typed bounded journal; never copy raw journal bytes into ZIP.
function Read-C545DMetadataReport([string]$journal,[string]$source,[datetime]$begin,[datetime]$end,$namer){
    $rows=New-Object 'System.Collections.Generic.List[object]'
    $result=[pscustomobject]@{
        status='not_found';rows=$rows;invalid_slots=0;busy_slots=0;saturated_slots=0;recovered_slots=0
        matches=0;mismatches=0;unknown=0;count_difference='not_classified'
        coverage='not_proven'
    }
    if(Test-Path -LiteralPath $journal -PathType Container){
        try{
            if(-not ('C545DMetadataJournalPrototype' -as [type])){Add-Type -Path $source -ErrorAction Stop}
            $snap=[C545DMetadataJournalPrototype]::ReadWindow($journal,$begin.ToUniversalTime(),$end.ToUniversalTime())
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
function Read-C545DWriterReport([string]$root,[string]$journalSource,[string]$writerSource,[datetime]$begin,[datetime]$end){
    $rows=New-Object 'System.Collections.Generic.List[object]'
    $r=[pscustomobject]@{status='not_found';rows=$rows;completed=0;unfinished=0;invalid=0;busy=0}
    if(-not $root -or -not(Test-Path -LiteralPath $root -PathType Container)){return $r}
    try{
        if(-not ('C545DWriterReceipts' -as [type])){
            Add-Type -Path @($journalSource,$writerSource) -ErrorAction Stop
        }
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
