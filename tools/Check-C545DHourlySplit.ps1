# One-shot read-only split diagnosis. No recorder stop/restart, media decode,
# credential export, live MP4 access, registry/DLL changes or network upload.
param([switch]$SelfTest)
$ErrorActionPreference='Stop'
function Read-BE([IO.BinaryReader]$r,[int]$n){
    $b=$r.ReadBytes($n)
    if($b.Length -ne $n){throw 'SHORT_HEADER'}
    [uint64]$v=0
    foreach($x in $b){$v=($v -shl 8) -bor [uint64]$x}
    return $v
}
function Find-Box([IO.BinaryReader]$r,[long]$begin,[long]$end,[string]$want){
    $s=$r.BaseStream
    $p=$begin
    for($i=0;$i -lt 4096 -and $p -lt $end;$i++){
        if($end-$p -lt 8){throw 'BOX_HEADER'}
        $s.Position=$p
        $size=Read-BE $r 4
        $type=[Text.Encoding]::ASCII.GetString($r.ReadBytes(4))
        $header=8
        if($size -eq 1){$size=Read-BE $r 8;$header=16}
        elseif($size -eq 0){$size=[uint64]($end-$p)}
        if($size -lt $header -or $size -gt [uint64]($end-$p)){throw 'BOX_SIZE'}
        $next=$p+[long]$size
        if($type -ceq $want){return [pscustomobject]@{Start=$p+$header;End=$next}}
        $p=$next
    }
    throw 'BOX_NOT_FOUND'
}
function Get-MovieDuration([string]$path){
    # Read lease excludes an existing writer and blocks new writes/deletes
    # only during this short header inspection; no media payload is read.
    $s=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try{
        $r=New-Object IO.BinaryReader($s)
        try{
            $moov=Find-Box $r 0 $s.Length 'moov'
            $mvhd=Find-Box $r $moov.Start $moov.End 'mvhd'
            if($mvhd.End-$mvhd.Start -lt 20){throw 'MVHD_SHORT'}
            $s.Position=$mvhd.Start
            $version=$r.ReadByte()
            if($version -eq 0){
                $s.Position=$mvhd.Start+12
                $scale=Read-BE $r 4;$dur=Read-BE $r 4
                if($dur -eq [uint32]::MaxValue){throw 'UNKNOWN_DURATION'}
            }elseif($version -eq 1){
                if($mvhd.End-$mvhd.Start -lt 32){throw 'MVHD_SHORT'}
                $s.Position=$mvhd.Start+20
                $scale=Read-BE $r 4;$dur=Read-BE $r 8
                if($dur -eq [uint64]::MaxValue){throw 'UNKNOWN_DURATION'}
            }else{throw 'MVHD_VERSION'}
            if($scale -eq 0 -or $dur -eq 0){throw 'UNKNOWN_DURATION'}
            return [pscustomobject]@{Seconds=[Math]::Round(([double]$dur/[double]$scale),3);Bytes=$s.Length}
        }finally{$r.Dispose()}
    }finally{$s.Dispose()}
}
function Get-SplitPolicy([string]$command){
    $result=[ordered]@{status='unknown';time_ns='unknown';bytes='unknown'}
    if([string]::IsNullOrEmpty($command) -or $command.Length -gt 32768){return [pscustomobject]$result}
    $m=[regex]::Matches($command,'(?i)(?:^|[\s"])splitmuxsink(?=[\s"])(.*?)(?=(?:[\s"])rtspsrc(?:[\s"]|$)|$)')
    if($m.Count -ne 1){return [pscustomobject]$result}
    $part=$m[0].Groups[1].Value
    if($part -notmatch '(?:^|[\s"])name=mux(?=[\s"]|$)'){return [pscustomobject]$result}
    foreach($kind in @('time','bytes')){
        $matches=[regex]::Matches($part,('(?:^|[\s"])max-size-'+$kind+'=([0-9]{1,20})(?=[\s"]|$)'))
        if($matches.Count -gt 1){return [pscustomobject]$result}
        $value=if($matches.Count -eq 1){$matches[0].Groups[1].Value}else{'not_explicit'}
        if($kind -eq 'time'){$result.time_ns=$value}else{$result.bytes=$value}
    }
    $result.status='observed_command_not_effective_properties'
    return [pscustomobject]$result
}
if($SelfTest){
    if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows'){throw 'CI_ONLY'}
    $dir=Join-Path $env:RUNNER_TEMP ('c545d-split-check-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $dir|Out-Null
    try{
        $p=Join-Path $dir 'test.mp4'
        # Small synthetic header-only fixtures, not playable media.
        $hex='000000246d6f6f760000001c6d766864000000000000000000000000000003e80036ee80'
        $b=[byte[]]$(for($i=0;$i -lt $hex.Length;$i+=2){[Convert]::ToByte($hex.Substring($i,2),16)})
        [IO.File]::WriteAllBytes($p,$b)
        $m=Get-MovieDuration $p
        if($m.Seconds -ne 3600 -or $m.Bytes -ne $b.Length){throw 'V0'}
        $hex='000000306d6f6f76000000286d7668640100000000000000000000000000000000000000000003e8000000000036ee80'
        $b=[byte[]]$(for($i=0;$i -lt $hex.Length;$i+=2){[Convert]::ToByte($hex.Substring($i,2),16)})
        [IO.File]::WriteAllBytes($p,$b)
        if((Get-MovieDuration $p).Seconds -ne 3600){throw 'V1'}
        $bad=$false
        [IO.File]::WriteAllBytes($p,[byte[]](0,0,0,99,109,111,111,118))
        try{[void](Get-MovieDuration $p)}catch{$bad=$true}
        if(-not $bad){throw 'MALFORMED'}
        $lock=[IO.File]::Open($p,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite)
        try{
            $blocked=$false
            try{[void](Get-MovieDuration $p)}catch [IO.IOException]{$blocked=$true}
            if(-not $blocked){throw 'WRITER_NOT_BLOCKED'}
        }finally{$lock.Dispose()}
        $policy=Get-SplitPolicy 'gst-launch-1.0.exe queue max-size-time=0 ! splitmuxsink name=mux location="C:\Synthetic\foo.mp4" max-size-time=3600000000000 max-size-bytes=0 async-finalize=false rtspsrc user-pw=SECRET ! queue max-size-bytes=8388608'
        if($policy.time_ns -ne '3600000000000' -or $policy.bytes -ne '0'){throw 'POLICY'}
        $policy=Get-SplitPolicy 'gst-launch-1.0.exe splitmuxsink name=mux max-size-time=3600000000000 rtspsrc queue max-size-bytes=8388608'
        if($policy.bytes -ne 'not_explicit'){throw 'DEFAULT_POLICY'}
        Write-Host 'C545D_SPLIT_CHECK_SELFTEST_PASS,v0=1,v1=1,malformed=1,writer_blocked=1,queue_excluded=1'
    }finally{Remove-Item -LiteralPath $dir -Recurse -Force}
    exit 0
}
$lines=New-Object 'Collections.Generic.List[string]'
$lines.Add('C545D_SPLIT_CHECK_V1')
$lines.Add('Read-only MP4 header inspection; no playback or media payload read.')
try{
    $procs=@(Get-CimInstance Win32_Process -Filter "Name = 'gst-launch-1.0.exe'" -OperationTimeoutSec 5)
    $lines.Add("gst_process_count=$($procs.Count)")
    if($procs.Count -eq 1){
        $policy=Get-SplitPolicy ([string]$procs[0].CommandLine)
        $lines.Add("command_policy=$($policy.status),time_ns=$($policy.time_ns),bytes=$($policy.bytes)")
    }
}catch{$lines.Add('command_policy=unavailable')}
try{
    $settings=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\settings.json'
    $cfg=Get-Content -LiteralPath $settings -Raw|ConvertFrom-Json
    $dir=New-Object IO.DirectoryInfo([string]$cfg.output_folder)
    if(-not $dir.Exists -or ($dir.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'DIRECTORY'}
    $recent=New-Object 'Collections.Generic.List[IO.FileInfo]'
    $seen=0;$limited=0
    foreach($f in $dir.EnumerateFiles('*.mp4',[IO.SearchOption]::TopDirectoryOnly)){
        $seen++
        if($seen -gt 50000){$limited=1;break}
        if($f.Name -cnotmatch '^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}_\d{2}-\d{2}(?:_\d{2,})?\.mp4$' -or
           ($f.Attributes -band [IO.FileAttributes]::ReparsePoint)){continue}
        if($f.LastWriteTimeUtc -lt [datetime]::UtcNow.AddDays(-3)){continue}
        $recent.Add($f)
        if($recent.Count -gt 8){
            $old=$recent|Sort-Object LastWriteTimeUtc|Select-Object -First 1
            [void]$recent.Remove($old)
        }
    }
    $lines.Add("enumeration_limited=$limited,selected=$($recent.Count)")
    $i=0
    foreach($f in ($recent|Sort-Object LastWriteTimeUtc)){
        $i++
        try{
            $m=Get-MovieDuration $f.FullName
            $wall=[Math]::Round(($f.LastWriteTimeUtc-$f.CreationTimeUtc).TotalSeconds,1)
            $lines.Add(('segment='+$i+',bytes='+$m.Bytes+',duration_s='+$m.Seconds.ToString([Globalization.CultureInfo]::InvariantCulture)+',file_wall_span_s='+$wall.ToString([Globalization.CultureInfo]::InvariantCulture)))
        }catch{$lines.Add("segment=$i,status=header_unavailable_or_busy")}
    }
}catch{$lines.Add('segments=unavailable')}
# Bounded transcript tails, no raw text, no command line or host path in output.
try{
    $logs=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Logs'
    $files=@(Get-ChildItem -LiteralPath $logs -File -Filter 'Recording_*.txt' -ErrorAction Stop|
        Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0}|
        Sort-Object LastWriteTimeUtc -Descending|Select-Object -First 2)
    $i=0
    foreach($file in $files){
        $i++
        try{
            $stream=[IO.File]::Open($file.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
            try{
                $n=[int][Math]::Min(262144L,$stream.Length)
                $stream.Position=$stream.Length-$n
                $reader=New-Object IO.BinaryReader($stream)
                $b=$reader.ReadBytes($n)
                $t=[Text.Encoding]::UTF8.GetString($b)
                if($t.IndexOf([char]0) -ge 0){
                    $t=[Text.Encoding]::Unicode.GetString($b)
                    if($t -notmatch 'GStreamer|Recording|PowerShell'){$t=[Text.Encoding]::Unicode.GetString($b,1,$b.Length-1)}
                }
                $launch=[regex]::Matches($t,'GStreamer launching \(EOS enabled\); attempt=').Count
                $retry=[regex]::Matches($t,'Recorder exit policy: reconnect').Count
                $stop=[regex]::Matches($t,'Recorder exit policy: stop').Count
                $ret=[regex]::Matches($t,'GStreamer returned; exitCode=').Count
                $lines.Add("log_tail=$i,launch=$launch,reconnect=$retry,stop=$stop,return=$ret,tail_only=1")
            }finally{$stream.Dispose()}
        }catch{$lines.Add("log_tail=$i,status=unavailable")}
    }
}catch{$lines.Add('log_tails=unavailable')}
$report=Join-Path $PSScriptRoot 'C545D_SPLIT_CHECK_RESULT.txt'
[IO.File]::WriteAllLines($report,$lines,[Text.Encoding]::UTF8)
$lines|ForEach-Object{Write-Host $_}
Write-Host 'Result saved: C545D_SPLIT_CHECK_RESULT.txt'
