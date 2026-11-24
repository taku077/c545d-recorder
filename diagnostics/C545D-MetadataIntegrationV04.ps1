# Optional v0.4 RC integration. Default OFF. Never initialize from manual rename/GUI.
# Requires a trusted, previously qualified direct ffprobe binary SHA256.
# A hash match verifies identity, not provenance. No automatic download or install.
$script:C545DMetadataWriterV04=$null
$script:C545DMetadataProbeV04=$null
$script:C545DMetadataProbeLengthV04=0L
$script:C545DMetadataProbeWriteV04=[datetime]::MinValue
function Initialize-C545DMetadataV04([string]$outputRoot,[string]$approvedSha256){
    try{
        if($approvedSha256 -notmatch '\A[0-9a-fA-F]{64}\z'){return 'probe_identity_unavailable'}
        $probe=Get-C545DProbeExe
        if(-not $probe){return 'probe_unavailable'}
        $item=Get-Item -LiteralPath $probe -ErrorAction Stop
        if($item.PSIsContainer -or $item.Name -ine 'ffprobe.exe' -or
           ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){return 'probe_rejected'}
        if(-not ('C545DClosedProbeV04' -as [type])){
            Add-Type -Path (Join-Path $PSScriptRoot 'C545DClosedProbeV04.cs') -ErrorAction Stop
        }
        if(-not [C545DClosedProbeV04]::IsSafeLocalDirectory([IO.Path]::GetFullPath($outputRoot)) -or
           -not [C545DClosedProbeV04]::IsSafeLocalDirectory($item.DirectoryName)){return 'root_rejected'}
        if((Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256 -ErrorAction Stop).Hash -ine $approvedSha256){return 'probe_identity_mismatch'}
        if(-not ('C545DMetadataWriterV04' -as [type])){
            Add-Type -Path @((Join-Path $PSScriptRoot 'C545DMetadataJournalV04.cs'),(Join-Path $PSScriptRoot 'C545DMetadataWriterV04.cs')) -ErrorAction Stop
        }
        $base=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer'
        $store=Join-Path $base 'MetadataV04'
        foreach($d in @($base,$store)){
            if(-not(Test-Path -LiteralPath $d -PathType Container)){
                $parent=[IO.Path]::GetDirectoryName($d)
                if(-not [C545DClosedProbeV04]::IsSafeLocalDirectory($parent)){return 'storage_root_rejected'}
                New-Item -ItemType Directory -Path $d -ErrorAction Stop|Out-Null
            }
            if(-not [C545DClosedProbeV04]::IsSafeLocalDirectory($d)){return 'storage_root_rejected'}
        }
        $journal=Join-Path $store 'journal';$receipts=Join-Path $store 'receipts'
        foreach($d in @($journal,$receipts)){
            if(-not(Test-Path -LiteralPath $d -PathType Container)){New-Item -ItemType Directory -Path $d -ErrorAction Stop|Out-Null}
            if(-not [C545DClosedProbeV04]::IsSafeLocalDirectory($d)){return 'storage_root_rejected'}
        }
        $script:C545DMetadataProbeV04=$item.FullName
        $script:C545DMetadataProbeLengthV04=$item.Length
        $script:C545DMetadataProbeWriteV04=$item.LastWriteTimeUtc
        $script:C545DMetadataWriterV04=New-Object C545DMetadataWriterV04($journal,$receipts)
        return 'enabled'
    }catch{
        $script:C545DMetadataProbeV04=$null
        return 'initialization_failed'
    }
}
function Get-C545DMetadataProbeV04([string]$root){
    if(-not $script:C545DMetadataWriterV04 -or -not $script:C545DMetadataProbeV04){return $null}
    try{
        $item=Get-Item -LiteralPath $script:C545DMetadataProbeV04 -ErrorAction Stop
        if($item.Length -ne $script:C545DMetadataProbeLengthV04 -or
           $item.LastWriteTimeUtc -ne $script:C545DMetadataProbeWriteV04 -or
           ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
           -not [C545DClosedProbeV04]::IsSafeLocalDirectory($root) -or
           -not [C545DClosedProbeV04]::IsSafeLocalDirectory($item.DirectoryName)){return $null}
        return $item.FullName
    }catch{return $null}
}
function Publish-C545DMetadataV04($observation){
    if(-not $script:C545DMetadataWriterV04){return}
    try{
        if($null -eq $observation){
            $row=ConvertTo-C545DMetadataEvidence '' 1
            $row.metadata_status='probe_unavailable'
        }else{$row=ConvertTo-C545DMetadataEvidence $observation.Json $observation.ExitCode}
        $entry=New-Object 'C545DMetadataJournalV04+Row'
        $entry.Utc=[datetime]::UtcNow;$entry.Status=$row.metadata_status
        $entry.DurationMs=$row.duration_ms
        $entry.VideoTracks=$row.video_tracks;$entry.AudioTracks=$row.audio_tracks
        $entry.Width=$row.width;$entry.Height=$row.height
        $entry.FpsNum=$row.fps_num;$entry.FpsDen=$row.fps_den
        $entry.SampleRate=$row.sample_rate;$entry.Channels=$row.channels
        $entry.H264=$row.video_h264;$entry.Aac=$row.audio_aac
        [void]$script:C545DMetadataWriterV04.TryPublish($entry)
    }catch{$script:C545DMetadataPublishErrorsV04++}
}
function Stop-C545DMetadataV04 {
    if(-not $script:C545DMetadataWriterV04){return 'not_enabled'}
    try{
        $w=$script:C545DMetadataWriterV04
        $drained=$w.Stop(250)
        Write-Host ('C545D_METADATA_V04_STOP,drained='+[int]$drained+',accepted='+$w.Accepted+
            ',saved='+$w.Saved+',rejected='+$w.Rejected+',failed='+$w.Failed+
            ',receipt='+$w.ReceiptStatus+',publish_errors='+$script:C545DMetadataPublishErrorsV04)
        if($drained){return 'drained'}
        return 'drain_unconfirmed'
    }catch{return 'stop_unconfirmed'}
}
$script:C545DMetadataPublishErrorsV04=0
