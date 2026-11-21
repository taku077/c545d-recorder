#Requires -Version 5.1
<#
CI ONLY: Render an isolated private MIRROR of the exact production Record.ps1.
This file NEVER invokes Record.ps1, gst-launch, a camera, or an installer.
Do not distribute the generated mirror to a Windows 10 user. Its source
contains an ephemeral CI path and does not implement host authorization.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$RecordSource,
  [Parameter(Mandatory=$true)][string]$SettingsSource,
  [Parameter(Mandatory=$true)][string]$StageRoot
)
$ErrorActionPreference='Stop'
$reason='BLOCKED';$rendered=0;$equivalent=0;$sourceSyntax=0;$candidatePinned=0
try {
  if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows' -or
     -not $env:RUNNER_TEMP){throw 'CI_ONLY'}
  $temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
  $stage=[IO.Path]::GetFullPath($StageRoot).TrimEnd('\')
  if(-not [string]::Equals([IO.Path]::GetDirectoryName($stage).TrimEnd('\'),
      $temp,[StringComparison]::OrdinalIgnoreCase) -or
     [IO.Path]::GetFileName($stage) -cnotmatch '^c545d-ci-production-mirror-[a-f0-9]{32}$'){
    throw 'UNSAFE_STAGE'
  }
  $stageItem=Get-Item -LiteralPath $stage -Force
  if(-not $stageItem.PSIsContainer -or
     ($stageItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
     [IO.File]::ReadAllText((Join-Path $stage '.c545d-ci-owned')) -cne 'CI_MIRROR_ONLY_NOT_FOR_EXECUTION'){
    throw 'UNOWNED_STAGE'
  }
  $bin=Join-Path $stage 'bin'
  $binItem=Get-Item -LiteralPath $bin -Force
  if(-not $binItem.PSIsContainer -or
     ($binItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){
    throw 'UNSAFE_BIN'
  }
  foreach($name in @('gst-launch-1.0.exe','gst-inspect-1.0.exe','gio-2.0-0.dll')){
    $file=Get-Item -LiteralPath (Join-Path $bin $name) -Force
    if($file.PSIsContainer -or
       ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){
      throw 'BAD_STAGED_INPUT'
    }
  }
  $expectedGio='67B9F7246E4744FEF7EE1EAD3BED4CE2179C6F0465EC68A92D01DD12B4A3CCAD'
  if((Get-FileHash -LiteralPath (Join-Path $bin 'gio-2.0-0.dll') -Algorithm SHA256).Hash -cne $expectedGio){
    throw 'CANDIDATE_DIFFERENT'
  }
  $candidatePinned=1
  if([IO.Path]::GetFileName($RecordSource) -cne 'Record.ps1' -or
     [IO.Path]::GetFileName($SettingsSource) -cne 'CommonSettings.ps1'){
    throw 'BAD_SOURCE_NAME'
  }
  $original=[IO.File]::ReadAllText((Resolve-Path -LiteralPath $RecordSource).Path)
  $settings=[IO.File]::ReadAllText((Resolve-Path -LiteralPath $SettingsSource).Path)
  $tokens=$null;$parseErrors=$null
  $ast=[Management.Automation.Language.Parser]::ParseInput($original,[ref]$tokens,[ref]$parseErrors)
  if($parseErrors.Count -ne 0){throw 'SOURCE_SYNTAX'}
  # AST restricts the only edit to an exact production Find-GstBin assignment.
  $found=@($ast.FindAll({param($node)
    $node -is [Management.Automation.Language.AssignmentStatementAst] -and
    $node.Left.Extent.Text -ceq '$bin' -and
    $node.Right.Extent.Text.Trim() -ceq 'Find-GstBin'
  },$true))
  if($found.Count -ne 1){throw 'BAD_ANCHOR'}
  foreach($term in @(
    "$"+'gst = Join-Path $bin '+"'gst-launch-1.0.exe'",
    "$"+'inspect = Join-Path $bin '+"'gst-inspect-1.0.exe'",
    "$"+'gstArgs = @('+"'-e') + "+'$pipeline.ToArray()',
    'Add-Input '+"'cam1' "+'$wideURL 0',
    'Add-Input '+"'cam2' "+'$teleURL 1',
    'max-size-time=3600000000000',
    "'.c545d-a-nonexistent-sentinel'"
  )){
    if($term -ceq "'.c545d-a-nonexistent-sentinel'"){continue}
    if(-not $original.Contains($term)){throw 'SOURCE_CHANGED'}
  }
  if(-not $original.Contains(". (Join-Path "+'$PSScriptRoot '+"'CommonSettings.ps1')")){
    throw 'SETTINGS_SOURCE_MISSING'
  }
  $anchor=$found[0].Extent
  $replacement='$bin = [IO.Path]::GetFullPath(''' + $bin.Replace("'","''") + ''')'
  $mirror=$original.Substring(0,$anchor.StartOffset)+$replacement+
          $original.Substring($anchor.EndOffset)
  # The equality after reversing precisely one AST edit is the contract:
  # no stream/audio/codec/mux/EOS/stop/reconnection statement can be mutated.
  $roundtrip=$mirror.Substring(0,$anchor.StartOffset)+$anchor.Text+
             $mirror.Substring($anchor.StartOffset+$replacement.Length)
  if($roundtrip -cne $original){throw 'ROUNDTRIP_DIFF'}
  $tokens2=$null;$errors2=$null
  [void][Management.Automation.Language.Parser]::ParseInput(
      $mirror,[ref]$tokens2,[ref]$errors2)
  if($errors2.Count -ne 0){throw 'MIRROR_SYNTAX'}
  $sourceSyntax=1
  $dst=Join-Path $stage 'Record.ps1'
  $dstSettings=Join-Path $stage 'CommonSettings.ps1'
  if((Test-Path -LiteralPath $dst) -or (Test-Path -LiteralPath $dstSettings)){
    throw 'OUTPUT_EXISTS'
  }
  $utf8=New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllText($dst,$mirror,$utf8)
  [IO.File]::WriteAllText($dstSettings,$settings,$utf8)
  if([IO.File]::ReadAllText($dst) -cne $mirror -or
     [IO.File]::ReadAllText($dstSettings) -cne $settings){throw 'MIRROR_DIFF'}
  $equivalent=1;$rendered=1;$reason='CI_ONLY_MIRROR_PASS'
} catch {
  $known=@('CI_ONLY','UNSAFE_STAGE','UNOWNED_STAGE','UNSAFE_BIN',
           'BAD_STAGED_INPUT','CANDIDATE_DIFFERENT','BAD_SOURCE_NAME',
           'SOURCE_SYNTAX','BAD_ANCHOR','SOURCE_CHANGED',
           'SETTINGS_SOURCE_MISSING','ROUNDTRIP_DIFF','MIRROR_SYNTAX',
           'OUTPUT_EXISTS','MIRROR_DIFF')
  if([string]$_.Exception.Message -in $known){
    $reason=[string]$_.Exception.Message
  } else {
    $reason='BLOCKED'
  }
}
Write-Output "C545D_PRODUCTION_MIRROR,rendered=$rendered,exact_one_statement=$equivalent,source_syntax=$sourceSyntax,candidate_pinned=$candidatePinned,host_executed=0,rtsp_contacted=0,install_approved=0,live_tapo_authorized=0,reason=$reason"
if($rendered -eq 1 -and $equivalent -eq 1 -and $candidatePinned -eq 1){exit 0}
exit 3
