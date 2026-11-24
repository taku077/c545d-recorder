# CI-only prototype. Do not dot-source from the recorder or ship in the EXE.
# Input is restricted ffprobe JSON, not a media path. No probe or host IO here.
function ConvertTo-C545DMetadataEvidence([string]$Json, [int]$ProbeExitCode) {
    $row=[ordered]@{
        metadata_status='unknown'; video_tracks=-1; audio_tracks=-1
        width=-1; height=-1; fps_num=-1; fps_den=-1
        sample_rate=-1; channels=-1; duration_ms=-1
        video_h264=-1; audio_aac=-1
        composition='not_collected'; av_sync='not_collected'
        full_decode='not_collected'; exact_hour='not_assessed'
    }
    if($ProbeExitCode -ne 0){$row.metadata_status='probe_failed';return [pscustomobject]$row}
    if([string]::IsNullOrWhiteSpace($Json) -or $Json.Length -gt 65536){
        $row.metadata_status='invalid_metadata';return [pscustomobject]$row
    }
    try{
        $doc=ConvertFrom-Json -InputObject $Json -ErrorAction Stop
        if($null -eq $doc -or $null -eq $doc.streams -or $null -eq $doc.format){throw 'shape'}
        $streams=@($doc.streams)
        if($streams.Count -lt 1 -or $streams.Count -gt 16){throw 'count'}
        $v=@($streams | Where-Object {$_.codec_type -ceq 'video'})
        $a=@($streams | Where-Object {$_.codec_type -ceq 'audio'})
        $row.video_tracks=$v.Count;$row.audio_tracks=$a.Count
        if($v.Count -ne 1 -or $a.Count -ne 1){
            $row.metadata_status='profile_mismatch';return [pscustomobject]$row
        }
        if([string]$v[0].codec_name -notmatch '^[a-zA-Z0-9_]{1,32}$' -or
           [string]$a[0].codec_name -notmatch '^[a-zA-Z0-9_]{1,32}$'){throw 'codec'}
        $row.video_h264=[int]($v[0].codec_name -ceq 'h264')
        $row.audio_aac=[int]($a[0].codec_name -ceq 'aac')
        $fields=@(
            @{key='width';value=$v[0].width}
            @{key='height';value=$v[0].height}
            @{key='sample_rate';value=$a[0].sample_rate}
            @{key='channels';value=$a[0].channels}
        )
        foreach($f in $fields){
            $n=0
            if([string]$f.value -notmatch '^[0-9]{1,9}$' -or
               -not [int]::TryParse([string]$f.value,[ref]$n) -or $n -le 0){throw 'integer'}
            $row[$f.key]=$n
        }
        if([string]$v[0].avg_frame_rate -notmatch '^([0-9]{1,9})/([0-9]{1,9})$'){throw 'rate'}
        $row.fps_num=[int]$Matches[1];$row.fps_den=[int]$Matches[2]
        if($row.fps_num -le 0 -or $row.fps_den -le 0){throw 'rate'}
        $duration=0.0
        if([string]$doc.format.duration -notmatch '^[0-9]{1,7}(\.[0-9]{1,9})?$' -or
           -not [double]::TryParse([string]$doc.format.duration,
              [Globalization.NumberStyles]::AllowDecimalPoint,
              [Globalization.CultureInfo]::InvariantCulture,[ref]$duration) -or
           $duration -le 0 -or $duration -gt 86400){throw 'duration'}
        $row.duration_ms=[long][Math]::Round($duration*1000)
        if($row.duration_ms -le 0){throw 'duration'}
        if($row.video_h264 -eq 1 -and $row.audio_aac -eq 1 -and
           $row.width -eq 2560 -and $row.height -eq 720 -and
           ([long]$row.fps_num -eq 15L * $row.fps_den) -and
           $row.sample_rate -eq 48000 -and $row.channels -eq 1){
            $row.metadata_status='profile_match_metadata_only'
        }else{$row.metadata_status='profile_mismatch'}
    }catch{$row.metadata_status='invalid_metadata'}
    return [pscustomobject]$row
}
function Test-C545DMetadataEvidence {
    $good='{"streams":[{"codec_type":"video","codec_name":"h264","width":2560,"height":720,"avg_frame_rate":"15/1"},{"codec_type":"audio","codec_name":"aac","sample_rate":"48000","channels":1}],"format":{"duration":"3600.123","filename":"rtsp://synthetic:secret@192.0.2.1/stream6"}}'
    $cases=@(
        @{json=$good;exit=0;expect='profile_match_metadata_only'}
        @{json=$good.Replace('15/1','30/2');exit=0;expect='profile_match_metadata_only'}
        @{json=$good.Replace('3600.123','0.5');exit=0;expect='profile_match_metadata_only'}
        @{json=$good.Replace('2560','1280');exit=0;expect='profile_mismatch'}
        @{json=$good.Replace('48000','44100');exit=0;expect='profile_mismatch'}
        @{json=$good.Replace('"channels":1','"channels":2');exit=0;expect='profile_mismatch'}
        @{json=$good.Replace('"aac"','"mp3"');exit=0;expect='profile_mismatch'}
        @{json=$good.Replace('"audio"','"data"');exit=0;expect='profile_mismatch'}
        @{json=$good.Replace('15/1','0/0');exit=0;expect='invalid_metadata'}
        @{json=$good.Replace('3600.123','N/A');exit=0;expect='invalid_metadata'}
        @{json=$good.Replace('3600.123','0');exit=0;expect='invalid_metadata'}
        @{json=$good.Replace('2560','"secret"');exit=0;expect='invalid_metadata'}
        @{json=$good;exit=1;expect='probe_failed'}
        @{json='{';exit=0;expect='invalid_metadata'}
        @{json=('x'*65537);exit=0;expect='invalid_metadata'}
    )
    foreach($case in $cases){
        $row=ConvertTo-C545DMetadataEvidence $case.json $case.exit
        if($row.metadata_status -cne $case.expect){throw 'METADATA_CLASSIFIER_CASE_FAILED'}
        if($row.composition -ne 'not_collected' -or $row.av_sync -ne 'not_collected' -or
           $row.full_decode -ne 'not_collected' -or $row.exact_hour -ne 'not_assessed'){
            throw 'METADATA_OVERCLAIM'
        }
        if(($row|ConvertTo-Json -Compress) -match 'rtsp|secret|192\.0\.2\.1|filename'){
            throw 'METADATA_PRIVACY_FAILURE'
        }
    }
    Write-Host ('C545D_METADATA_CLASSIFIER_PASS,cases='+$cases.Count+',media_decode_claim=0,host_modified=0')
}
