# Actual RC source, not an injected prototype. Private Actions fixture only.
param([Parameter(Mandatory=$true)][string]$FixtureDirectory,
      [Parameter(Mandatory=$true)][string]$ProbeExe)
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows'){throw 'CI_ONLY'}
$repo=Split-Path -Parent $PSScriptRoot
$root=Join-Path $FixtureDirectory 'actual-v04'
New-Item -ItemType Directory -Path $root|Out-Null
$sample=Join-Path $FixtureDirectory '2026-11-24_12-00_12-01.mp4'
$hash=(Get-FileHash -LiteralPath $sample).Hash
$approved=(Get-FileHash -LiteralPath $ProbeExe).Hash
function Eq($a,$b,[string]$tag){if($a -cne $b){throw ('V04_RC_ASSERT_'+$tag+' actual='+$a+' expected='+$b)}}
function Await([scriptblock]$p,[int]$ms,[string]$tag){
    $clock=[Diagnostics.Stopwatch]::StartNew()
    do{if(& $p){return};Start-Sleep -Milliseconds 100}while($clock.ElapsedMilliseconds -lt $ms)
    throw ('V04_RC_TIMEOUT_'+$tag)
}
function Run-Arm([string]$mode){
    $arm=Join-Path $root $mode
    $output=Join-Path $arm 'output';$local=Join-Path $arm 'local'
    foreach($dir in @($output,$local)){New-Item -ItemType Directory -Path $dir -Force|Out-Null}
    $ready=Join-Path $arm 'ready';$stop=Join-Path $arm 'stop'
    $oldPath=$env:PATH;$oldLocal=$env:LOCALAPPDATA
    $env:PATH=(Split-Path -Parent $ProbeExe)+';'+$oldPath;$env:LOCALAPPDATA=$local
    $proc=$null
    try{
        $psi=New-Object Diagnostics.ProcessStartInfo
        $psi.FileName=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $scriptPath=Join-Path $repo 'SegmentNamerWorker.ps1'
        $psi.Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$scriptPath+
          '" -OutputDirectory "'+$output+'" -OwnerProcessId '+$PID+' -ReadyFile "'+$ready+'" -StopFile "'+$stop+'"'
        if($mode -eq 'enabled'){$psi.Arguments+=' -EnableMetadataDiagnostics -MetadataProbeSha256 '+$approved}
        if($mode -eq 'mismatch'){$psi.Arguments+=' -EnableMetadataDiagnostics -MetadataProbeSha256 '+('0'*64)}
        $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true
        $psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
        $proc=[Diagnostics.Process]::Start($psi);$null=$proc.Handle
        $out=$proc.StandardOutput.ReadToEndAsync();$err=$proc.StandardError.ReadToEndAsync()
        Await {(Test-Path -LiteralPath $ready) -or $proc.HasExited} 20000 'READY'
        if($proc.HasExited){throw 'V04_RC_EARLY_EXIT'}
        $pending=Join-Path $output 'C545D_PENDING_20261124_120000_12345678_00001.mp4'
        Copy-Item -LiteralPath $sample -Destination $pending
        Await {-not(Test-Path -LiteralPath $pending)} 15000 'RENAME'
        [IO.File]::WriteAllText($stop,'CI_TEST')
        if(-not $proc.WaitForExit(16000)){throw 'V04_RC_EXIT_TIMEOUT'}
        $proc.Refresh();Eq $proc.ExitCode 0 'EXIT'
        if(-not $out.Wait(1000) -or -not $err.Wait(1000)){throw 'V04_RC_PIPE_TIMEOUT'}
        $files=@(Get-ChildItem -LiteralPath $output -File)
        Eq $files.Count 1 'FILE_COUNT'
        Eq (Get-FileHash -LiteralPath $files[0].FullName).Hash $hash 'HASH'
        $store=Join-Path $local 'C545D_GStreamer\MetadataV04'
        $log=Get-Content (Join-Path $local 'C545D_GStreamer\Logs\Filename_Rename.log') -Raw
        if($mode -eq 'enabled'){
            if($log -notmatch 'Metadata v0.4 initialization: enabled'){throw 'V04_RC_INIT_NOT_ENABLED'}
            if($out.Result -notmatch 'C545D_METADATA_V04_STOP,drained=1,accepted=1,saved=1,rejected=0,failed=0,receipt=final_saved,publish_errors=0'){throw 'V04_RC_COUNTERS'}
            $j=@(Get-ChildItem (Join-Path $store 'journal') -File);Eq $j.Count 1 'JOURNAL'
            $lines=@(Get-Content -LiteralPath $j[0].FullName);Eq $lines.Count 2 'ROWS'
            if($lines[1] -notmatch '\|profile_match_metadata_only\|'){throw 'V04_RC_PROFILE'}
            $receipts=@(Get-ChildItem (Join-Path $store 'receipts') -File);Eq $receipts.Count 1 'RECEIPT'
            Eq @(Get-Content -LiteralPath $receipts[0].FullName).Count 2 'FINAL_RECEIPT'
        }else{
            Eq (Test-Path -LiteralPath $store) $false 'NO_METADATA_STORAGE'
            if($mode -eq 'mismatch' -and $log -notmatch 'Metadata v0.4 initialization: probe_identity_mismatch'){throw 'V04_RC_MISMATCH_NOT_REPORTED'}
            if($mode -eq 'disabled' -and $log -match 'Metadata v0.4 initialization:'){throw 'V04_RC_DEFAULT_CHANGED'}
        }
        Write-Host ('C545D_V04_ACTUAL_NAMER_ARM_PASS,mode='+$mode+',renamed=1,hash_unchanged=1,exit=0')
    }finally{
        if($proc){if(-not $proc.HasExited){$proc.Kill();[void]$proc.WaitForExit(3000)};$proc.Dispose()}
        $env:PATH=$oldPath;$env:LOCALAPPDATA=$oldLocal
    }
}
Run-Arm 'disabled'
Run-Arm 'mismatch'
Run-Arm 'enabled'
Write-Host 'C545D_V04_ACTUAL_NAMER_PASS,arms=3,default_off=1,identity_mismatch_fallback=1,enabled_saved=1,real_camera=0,install_approved=0'
