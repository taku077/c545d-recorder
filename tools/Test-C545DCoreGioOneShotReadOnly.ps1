#Requires -Version 5.1
<#
.SYNOPSIS
One-shot read-only, fail-closed Windows 10 GIO candidate inventory.
.DESCRIPTION
Runs TWO existing read-only checkers without starting or stopping GStreamer,
copying or loading DLLs, changing PATH/registry or examining RTSP credentials.
Only one bounded numeric line is emitted. Does not authorize installation.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$GStreamerBin,
  [Parameter(Mandatory=$true)][string]$CandidateDll,
  [Parameter(Mandatory=$true)][string]$CandidateManifest,
  [Parameter(Mandatory=$true)][string]$CoreReferenceManifest
)
$ErrorActionPreference='Stop'
$reason='INCOMPLETE_CHECK'
$preValid=0;$graphValid=0;$preExit=-1;$graphExit=-1
$preReady=0;$graphMatch=0;$active=1;$win10=0
$candidateConsistent=0;$referenceConsistent=0;$readOnlyReady=0

function Parse-StrictRecord([object[]]$rows,[string]$prefix,[string[]]$keys) {
  if($rows.Count -ne 1 -or $null -eq $rows[0]){throw 'unexpected child line count'}
  $line=[string]$rows[0]
  if(-not $line.StartsWith(($prefix+','),[StringComparison]::Ordinal)){throw 'wrong child prefix'}
  if($line.Length -gt 650){throw 'oversized child output'}
  $parts=$line.Split(',')
  if($parts.Count -ne ($keys.Count+1)){throw 'unexpected child columns'}
  $values=@{}
  for($i=0;$i -lt $keys.Count;$i++){
    $split=$parts[$i+1].Split('=')
    if($split.Count -ne 2 -or $split[0] -cne $keys[$i]){throw 'wrong child key'}
    if($split[1] -notmatch '^[A-Z0-9_]+$'){throw 'unsafe or malformed child value'}
    $values[$split[0]]=$split[1]
  }
  return $values
}

try {
  $scriptDir=Split-Path -Parent $MyInvocation.MyCommand.Path
  $preScript=Join-Path $scriptDir 'Test-C545DCoreGioReadOnly.ps1'
  $graphScript=Join-Path $scriptDir 'Test-C545DCoreGioDependencyGraphReadOnly.ps1'
  # The wrapper may run under pwsh 7 on CI, but both original scripts are
  # pinned to the Windows PowerShell 5.1 runtime and its tested semantics.
  $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  if(-not (Test-Path -LiteralPath $ps -PathType Leaf) -or
     -not (Test-Path -LiteralPath $preScript -PathType Leaf) -or
     -not (Test-Path -LiteralPath $graphScript -PathType Leaf)){
    throw 'required checker unavailable'
  }
  $preRows=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $preScript -GStreamerBin $GStreamerBin -CandidateDll $CandidateDll -ManifestFile $CandidateManifest 2>$null)
  $preExit=$LASTEXITCODE
  $pre=Parse-StrictRecord $preRows 'C545D_CORE_GIO_PREFLIGHT' @('inputs','candidate_sha','reference_sha','pe_x64','runtime_exes','active_recorder','windows10','compatible','read_only_eligibility','install_approved','reason')
  if($preExit -notin @(0,3) -or $pre.install_approved -ne '0' -or
     $pre.reason -notin @('MISSING_INPUT','BAD_CANDIDATE','UNKNOWN_INSTALLED_RUNTIME',
       'RUNTIME_EXECUTABLE_MISSING','PROVENANCE_MISSING','RECORDER_ACTIVE',
       'WIN10_NOT_VERIFIED','READ_ONLY_COMPATIBILITY_ONLY','INPUT_READ_ERROR')){
    throw 'untrusted main checker result'
  }
  foreach($k in @('inputs','candidate_sha','reference_sha','pe_x64','runtime_exes','active_recorder','windows10','compatible','read_only_eligibility')){
    if($pre[$k] -notin @('0','1')){throw 'malformed main checker boolean'}
  }
  if(($pre.read_only_eligibility -eq '1') -ne ($preExit -eq 0)){
    throw 'main checker exit/status inconsistency'
  }
  $preValid=1
  $preReady=[int]$pre.read_only_eligibility
  $active=[int]$pre.active_recorder
  $win10=[int]$pre.windows10

  $graphRows=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $graphScript -GStreamerBin $GStreamerBin -CandidateDll $CandidateDll -ReferenceManifest $CoreReferenceManifest 2>$null)
  $graphExit=$LASTEXITCODE
  $graph=Parse-StrictRecord $graphRows 'C545D_GIO_CORE_GRAPH_PREFLIGHT' @('manifest_valid','core_found','core_hash_matched','core_pe_x64','missing','hash_mismatch','invalid_pe','candidate_valid','graph_match','install_approved','reason')
  if($graphExit -notin @(0,3) -or $graph.install_approved -ne '0' -or
     $graph.reason -notin @('UNREADABLE_INPUT','MISSING_CORE_DLL',
       'UNKNOWN_RUNTIME_DLL_HASH','INVALID_CORE_DLL_PE','BAD_CANDIDATE',
       'READ_ONLY_GRAPH_MATCH','INVALID_REFERENCE_MANIFEST')){
    throw 'untrusted dependency checker result'
  }
  foreach($k in @('manifest_valid','candidate_valid','graph_match')){
    if($graph[$k] -notin @('0','1')){throw 'malformed graph boolean'}
  }
  foreach($k in @('core_found','core_hash_matched','core_pe_x64','missing','hash_mismatch','invalid_pe')){
    if($graph[$k] -notmatch '^\d{1,3}$'){throw 'malformed graph count'}
  }
  if(($graph.graph_match -eq '1') -ne ($graphExit -eq 0)){
    throw 'dependency checker exit/status inconsistency'
  }
  $graphValid=1
  $graphMatch=[int]$graph.graph_match
  $candidateConsistent=[int]($pre.candidate_sha -eq '1' -and $pre.pe_x64 -eq '1' -and $graph.candidate_valid -eq '1')
  $referenceConsistent=[int]($pre.reference_sha -eq '1' -and $graph.manifest_valid -eq '1' -and $graph.core_hash_matched -eq '6')
  $readOnlyReady=[int]($preReady -eq 1 -and $graphMatch -eq 1 -and $candidateConsistent -eq 1 -and $referenceConsistent -eq 1)

  if($readOnlyReady -eq 1){$reason='READ_ONLY_MATCH_ONLY'}
  elseif($candidateConsistent -ne 1){$reason='CANDIDATE_NOT_QUALIFIED'}
  elseif($pre.inputs -eq '0' -or [int]$graph.missing -gt 0){$reason='MISSING_INPUT'}
  elseif($referenceConsistent -ne 1 -or $graphMatch -ne 1){$reason='UNKNOWN_INSTALLED_RUNTIME'}
  elseif($active -eq 1){$reason='RECORDER_ACTIVE'}
  elseif($win10 -eq 0){$reason='WIN10_NOT_VERIFIED'}
  else{$reason='NOT_ELIGIBLE'}
} catch {
  # No host path, command line, local DLL hash, or error message is printed.
  $readOnlyReady=0
  $reason='INCOMPLETE_CHECK'
}
$line=('C545D_ONE_SHOT_GIO_READONLY,preflight_valid={0},graph_valid={1},'+
       'preflight_exit={2},graph_exit={3},candidate_consistent={4},'+
       'reference_consistent={5},graph_match={6},recorder_active={7},'+
       'windows10={8},read_only_eligible={9},install_approved=0,'+
       'smoke_authorized=0,reason={10}') -f $preValid,$graphValid,
       $preExit,$graphExit,$candidateConsistent,$referenceConsistent,
       $graphMatch,$active,$win10,$readOnlyReady,$reason
Write-Output $line
if($readOnlyReady -eq 1){exit 0}
exit 3
