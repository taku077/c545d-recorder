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
    $oldOpt=$env:C545D_METADATA_V04;$oldSha=$env:C545D_METADATA_PROBE_SHA256
    $env:C545D_METADATA_V04=$null;$env:C545D_METADATA_PROBE_SHA256=$null
    if($mode -in @('env_enabled','lease_busy','missing_module','explicit_off')){
        $env:C545D_METADATA_V04='1';$env:C545D_METADATA_PROBE_SHA256=$approved
    }
    if($mode -eq 'env_invalid'){
        $env:C545D_METADATA_V04='1';$env:C545D_METADATA_PROBE_SHA256='invalid'
    }
    $env:PATH=(Split-Path -Parent $ProbeExe)+';'+$oldPath;$env:LOCALAPPDATA=$local
    $proc=$null;$lease=$null
    try{
        if($mode -eq 'lease_busy'){
            $dir=Join-Path $local 'C545D_GStreamer\MetadataV04'
            New-Item -ItemType Directory -Path $dir -Force|Out-Null
            $lease=[IO.File]::Open((Join-Path $dir 'writer.lease'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        }
        $psi=New-Object Diagnostics.ProcessStartInfo
        $psi.FileName=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $scriptPath=Join-Path $repo 'SegmentNamerWorker.ps1'
        if($mode -eq 'missing_module'){
            $mirror=Join-Path $arm 'missing-module-source'
            New-Item -ItemType Directory -Path $mirror|Out-Null
            foreach($name in @('SegmentNamerWorker.ps1','SegmentNamer.ps1')){
                Copy-Item -LiteralPath (Join-Path $repo $name) -Destination $mirror
            }
            $scriptPath=Join-Path $mirror 'SegmentNamerWorker.ps1'
        }
        $psi.Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$scriptPath+
          '" -OutputDirectory "'+$output+'" -OwnerProcessId '+$PID+' -ReadyFile "'+$ready+'" -StopFile "'+$stop+'"'
        if($mode -eq 'enabled'){$psi.Arguments+=' -EnableMetadataDiagnostics -MetadataProbeSha256 '+$approved}
        if($mode -eq 'mismatch'){$psi.Arguments+=' -EnableMetadataDiagnostics -MetadataProbeSha256 '+('0'*64)}
        if($mode -eq 'explicit_off'){$psi.Arguments+=' -MetadataProbeSha256 '+$approved}
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
        if($mode -in @('enabled','env_enabled')){
            if($log -notmatch 'Metadata v0.4 initialization: enabled'){throw 'V04_RC_INIT_NOT_ENABLED'}
            if($out.Result -notmatch 'C545D_METADATA_V04_STOP,drained=1,accepted=1,saved=1,rejected=0,failed=0,receipt=final_saved,publish_errors=0'){throw 'V04_RC_COUNTERS'}
            $j=@(Get-ChildItem (Join-Path $store 'journal') -File);Eq $j.Count 1 'JOURNAL'
            $lines=@(Get-Content -LiteralPath $j[0].FullName);Eq $lines.Count 2 'ROWS'
            if($lines[1] -notmatch '\|profile_match_metadata_only\|'){throw 'V04_RC_PROFILE'}
            $receipts=@(Get-ChildItem (Join-Path $store 'receipts') -File);Eq $receipts.Count 1 'RECEIPT'
            Eq @(Get-Content -LiteralPath $receipts[0].FullName).Count 2 'FINAL_RECEIPT'
            $released=[IO.File]::Open((Join-Path $store 'writer.lease'),[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
            $released.Dispose()
        }elseif($mode -eq 'lease_busy'){
            if($log -notmatch 'Metadata v0.4 initialization: writer_lease_unavailable'){throw 'V04_RC_LEASE_NOT_REPORTED'}
            Eq (Test-Path -LiteralPath (Join-Path $store 'journal')) $false 'LEASE_NO_WRITER'
            Eq (Test-Path -LiteralPath (Join-Path $store 'receipts')) $false 'LEASE_NO_RECEIPT'
        }else{
            Eq (Test-Path -LiteralPath $store) $false 'NO_METADATA_STORAGE'
            if($mode -eq 'mismatch' -and $log -notmatch 'Metadata v0.4 initialization: probe_identity_mismatch'){throw 'V04_RC_MISMATCH_NOT_REPORTED'}
            if($mode -in @('disabled','env_invalid','explicit_off') -and $log -match 'Metadata v0.4 initialization:'){throw 'V04_RC_DEFAULT_CHANGED'}
            if($mode -eq 'missing_module' -and $log -notmatch 'Metadata v0.4 initialization: initialization_failed'){throw 'V04_RC_MISSING_MODULE_NOT_REPORTED'}
        }
        Write-Host ('C545D_V04_ACTUAL_NAMER_ARM_PASS,mode='+$mode+',renamed=1,hash_unchanged=1,exit=0')
    }finally{
        if($proc){if(-not $proc.HasExited){$proc.Kill();[void]$proc.WaitForExit(3000)};$proc.Dispose()}
        if($lease){$lease.Dispose()}
        $env:PATH=$oldPath;$env:LOCALAPPDATA=$oldLocal
        $env:C545D_METADATA_V04=$oldOpt;$env:C545D_METADATA_PROBE_SHA256=$oldSha
    }
}
Run-Arm 'disabled'
Run-Arm 'mismatch'
Run-Arm 'enabled'
Run-Arm 'env_enabled'
Run-Arm 'env_invalid'
Run-Arm 'explicit_off'
Run-Arm 'lease_busy'
Run-Arm 'missing_module'
Write-Host 'C545D_V04_ACTUAL_NAMER_PASS,arms=8,default_off=1,identity_mismatch_fallback=1,enabled_saved=1,env_optin=1,invalid_env_off=1,explicit_precedence=1,lease_busy_fallback=1,missing_module_fallback=1,real_camera=0,install_approved=0'
