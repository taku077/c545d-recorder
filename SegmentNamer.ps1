# C545D GStreamer - finalized-MP4 renamer.
# Normal operation: FileSystemWatcher sends specific paths to Invoke-C545DRenameOne.
# Get-ChildItem enumeration is retained ONLY for explicit manual recovery.
# Existing completed recordings with user-selected names are left untouched.
$script:C545DProbePath = $null
$script:C545DProbeSearched = $false
$script:C545DNamerLogDir = Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Logs'
$script:C545DNamerLastError = ''

function Write-C545DNamerLog([string]$line) {
    try {
        if (-not (Test-Path -LiteralPath $script:C545DNamerLogDir)) {
            New-Item -ItemType Directory -Force -Path $script:C545DNamerLogDir | Out-Null
        }
        $path = Join-Path $script:C545DNamerLogDir 'Filename_Rename.log'
        Add-Content -LiteralPath $path -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $line) -Encoding UTF8
    } catch { }
}

function Get-C545DProbeExe {
    if (-not $script:C545DProbeSearched) {
        $script:C545DProbeSearched = $true
        $cmd = Get-Command 'ffprobe.exe' -ErrorAction SilentlyContinue
        if ($cmd) { $script:C545DProbePath = $cmd.Source }
        else {
            $candidates = @('C:\ffmpeg\bin\ffprobe.exe',
                            (Join-Path $env:LOCALAPPDATA 'Programs\ffmpeg\bin\ffprobe.exe'),
                            (Join-Path $env:ProgramFiles 'ffmpeg\bin\ffprobe.exe'),
                            (Join-Path $env:USERPROFILE 'scoop\apps\ffmpeg\current\bin\ffprobe.exe'))
            if (${env:ProgramFiles(x86)}) {
                $candidates += (Join-Path ${env:ProgramFiles(x86)} 'ffmpeg\bin\ffprobe.exe')
            }
            foreach ($candidate in $candidates) {
                if (Test-Path -LiteralPath $candidate) { $script:C545DProbePath = $candidate; break }
            }
        }
        if (-not $script:C545DProbePath) {
            Write-C545DNamerLog 'ffprobe not found. Closed files will be named using their write timestamps.'
        }
    }
    return $script:C545DProbePath
}

function Get-C545DDuration([string]$path) {
    $probe = Get-C545DProbeExe
    if (-not $probe) { return $null }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $probe
    $psi.Arguments = '-v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 -i "' + $path.Replace('"','\"') + '"'
    $psi.CreateNoWindow = $true
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $p = $null
    try {
        $p = [System.Diagnostics.Process]::Start($psi)
        if (-not $p.WaitForExit(4000)) {
            try { $p.Kill() } catch { }
            return $null
        }
        $out = $p.StandardOutput.ReadToEnd().Trim()
        if ($p.ExitCode -ne 0) { return $null }
        $duration = 0.0
        if ([double]::TryParse($out,
            [System.Globalization.NumberStyles]::Float,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$duration) -and $duration -gt 0) {
            return $duration
        }
        return $null
    }
    catch { return $null }
    finally { if ($p) { $p.Dispose() } }
}

# Temporary names emitted by Record.ps1. Never touch other MP4s.
function Test-C545DTempName([string]$Name) {
    return (($Name -cmatch '^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}-\d{3}_\d{5}\.mp4$') -or
            ($Name -cmatch '^C545D_PENDING_\d{8}_\d{6}_[0-9a-fA-F]{8}_\d{5}\.mp4$'))
}

# Return done / pending / skip / error; never block the recorder.
function Invoke-C545DRenameOne([string]$FullPath, [string]$OutputDirectory) {
    if ([string]::IsNullOrWhiteSpace($FullPath) -or [string]::IsNullOrWhiteSpace($OutputDirectory)) { return 'skip' }
    try {
        $root=[System.IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
        $parent=[System.IO.Path]::GetFullPath([System.IO.Path]::GetDirectoryName($FullPath)).TrimEnd('\')
        if (-not [string]::Equals($root,$parent,[StringComparison]::OrdinalIgnoreCase)) { return 'skip' }
        $name=[System.IO.Path]::GetFileName($FullPath)
        if (-not (Test-C545DTempName $name)) { return 'skip' }
        if (-not (Test-Path -LiteralPath $FullPath -PathType Leaf)) { return 'skip' }
        $file=Get-Item -LiteralPath $FullPath -ErrorAction Stop
        if ($file.Length -lt 1024) { return 'pending' }

        # Created is NOT completion. This exclusive-open check is essential:
        # async-finalize may still be writing the previous MP4.
        $handle=$null
        try {
            $handle=[System.IO.File]::Open($file.FullName, [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        } catch { return 'pending' }
        finally { if ($handle) { $handle.Dispose() } }

        # Verify MP4 indexing before rename when ffprobe is available.
        $metaObservationV04=$null
        $metaProbeV04=$null
        if($script:C545DMetadataWriterV04){
            try{$metaProbeV04=Get-C545DMetadataProbeV04 $root}catch{}
        }
        if($metaProbeV04){
            $duration=$null
            try{
                $metaObservationV04=[C545DClosedProbeV04]::ProbeRenameCandidate($root,$name,$true,$metaProbeV04,4000)
                if($metaObservationV04.Status -eq 'ok'){
                    $doc=ConvertFrom-Json -InputObject $metaObservationV04.Json -ErrorAction Stop
                    $d=0.0
                    if([double]::TryParse([string]$doc.format.duration,
                        [Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,
                        [ref]$d) -and $d -gt 0 -and -not [double]::IsInfinity($d)){$duration=$d}
                }
            }catch{}
        }else{
        $duration=Get-C545DDuration $file.FullName
        }
        if ((Get-C545DProbeExe) -and $null -eq $duration) { return 'pending' }
        $file.Refresh()
        $begin=$file.CreationTime
        $ending=$file.LastWriteTime
        if ($null -ne $duration) { $ending=$begin.AddSeconds([double]$duration) }
        if ($ending -lt $begin) { $ending=$begin }
        $stem=('{0:yyyy-MM-dd_HH-mm}_{1:HH-mm}' -f $begin,$ending)
        $dest=Join-Path $OutputDirectory ($stem + '.mp4')
        $index=2
        while (Test-Path -LiteralPath $dest) {
            $dest=Join-Path $OutputDirectory ('{0}_{1:00}.mp4' -f $stem,$index)
            $index++
        }
        # Move within the same directory: no media stream is decoded or re-encoded.
        Move-Item -LiteralPath $file.FullName -Destination $dest -ErrorAction Stop
        Write-C545DNamerLog ('Renamed (closed): ' + $name + ' -> ' + (Split-Path -Leaf $dest))
        if($script:C545DMetadataWriterV04){
            try{Publish-C545DMetadataV04 $metaObservationV04}catch{}
        }
        return 'done'
    }
    catch {
        Write-C545DNamerLog ('Rename deferred (' + [IO.Path]::GetFileName($FullPath) + '): ' + $_.Exception.Message)
        return 'pending'
    }
}

# ONLY invoked when the user manually requests recovery. Never scheduled.
function Invoke-C545DRenameSegments([string]$OutputDirectory) {
    if ([string]::IsNullOrWhiteSpace($OutputDirectory) -or
        -not (Test-Path -LiteralPath $OutputDirectory -PathType Container)) { return }
    $items=Get-ChildItem -LiteralPath $OutputDirectory -File -Filter '*.mp4' -ErrorAction Stop
    foreach ($file in $items) {
        if (-not (Test-C545DTempName $file.Name)) { continue }
        [void](Invoke-C545DRenameOne -FullPath $file.FullName -OutputDirectory $OutputDirectory)
    }
}
