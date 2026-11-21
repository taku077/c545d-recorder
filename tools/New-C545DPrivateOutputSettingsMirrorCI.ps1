#Requires -Version 5.1
<#
CI ONLY. Add a single private output-folder assignment to a CI-owned
CommonSettings.ps1 mirror; NEVER change the production settings or recording.
No RTSP, camera password, live recorder or original output directory touched.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$StageRoot,
  [Parameter(Mandatory=$true)][string]$OriginalSettingsSource
)
$ErrorActionPreference='Stop'
$patched=0;$singleOverride=0;$syntax=0;$reason='BLOCKED'
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
  $dir=Get-Item -LiteralPath $stage -Force
  if(-not $dir.PSIsContainer -or
     ($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
     [IO.File]::ReadAllText((Join-Path $stage '.c545d-ci-owned')) -cne
       'CI_MIRROR_ONLY_NOT_FOR_EXECUTION'){throw 'UNOWNED_STAGE'}
  if([IO.Path]::GetFileName($OriginalSettingsSource) -cne 'CommonSettings.ps1'){
    throw 'BAD_SOURCE_NAME'
  }
  $dst=Join-Path $stage 'CommonSettings.ps1'
  $original=[IO.File]::ReadAllText((Resolve-Path -LiteralPath $OriginalSettingsSource).Path)
  if([IO.File]::ReadAllText((Resolve-Path -LiteralPath $dst).Path) -cne $original){
    throw 'SOURCE_ALREADY_CHANGED'
  }
  $tokens=$null;$errors=$null
  $ast=[Management.Automation.Language.Parser]::ParseInput($original,[ref]$tokens,[ref]$errors)
  if($errors.Count -ne 0){throw 'SOURCE_SYNTAX'}
  $funcs=@($ast.FindAll({param($n)
    $n -is [Management.Automation.Language.FunctionDefinitionAst] -and
    $n.Name -ceq 'Read-C545DSettings'
  },$true))
  if($funcs.Count -ne 1){throw 'FUNCTION_NOT_UNIQUE'}
  $returns=@($funcs[0].FindAll({param($n)
    $n -is [Management.Automation.Language.ReturnStatementAst] -and
    $n.Extent.Text.Trim() -ceq 'return $s'
  },$true))
  if($returns.Count -ne 1){throw 'RETURN_NOT_UNIQUE'}
  $output=Join-Path $stage 'private-output'
  if(Test-Path -LiteralPath $output){throw 'OUTPUT_EXISTS'}
  # A harmless, empty, CI-owned child folder; no production MP4 is touched.
  New-Item -ItemType Directory -Path $output | Out-Null
  $item=Get-Item -LiteralPath $output -Force
  if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'OUTPUT_LINKED'}
  $injection='$s.output_folder = ''' + $output.Replace("'","''") + '''' + [Environment]::NewLine + '    '
  $anchor=$returns[0].Extent.StartOffset
  $patchedSource=$original.Substring(0,$anchor)+$injection+$original.Substring($anchor)
  $roundtrip=$patchedSource.Substring(0,$anchor)+
             $patchedSource.Substring($anchor+$injection.Length)
  if($roundtrip -cne $original){throw 'NONLOCAL_CHANGE'}
  $tokens2=$null;$errors2=$null
  [void][Management.Automation.Language.Parser]::ParseInput(
    $patchedSource,[ref]$tokens2,[ref]$errors2)
  if($errors2.Count -ne 0){throw 'MIRROR_SYNTAX'}
  $syntax=1
  $utf8=New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllText($dst,$patchedSource,$utf8)
  if([IO.File]::ReadAllText($dst) -cne $patchedSource){throw 'WRITE_DIFFERENT'}
  $singleOverride=1;$patched=1;$reason='CI_PRIVATE_OUTPUT_MIRROR_PASS'
} catch {
  $known=@('CI_ONLY','UNSAFE_STAGE','UNOWNED_STAGE','BAD_SOURCE_NAME',
    'SOURCE_ALREADY_CHANGED','SOURCE_SYNTAX','FUNCTION_NOT_UNIQUE',
    'RETURN_NOT_UNIQUE','OUTPUT_EXISTS','OUTPUT_LINKED','NONLOCAL_CHANGE',
    'MIRROR_SYNTAX','WRITE_DIFFERENT')
  if([string]$_.Exception.Message -in $known){
    $reason=[string]$_.Exception.Message
  }
}
Write-Output "C545D_PRIVATE_OUTPUT_MIRROR,patched=$patched,single_assignment=$singleOverride,source_syntax=$syntax,private_only=1,host_executed=0,rtsp_contacted=0,install_approved=0,live_tapo_authorized=0,reason=$reason"
if($patched -eq 1 -and $singleOverride -eq 1){exit 0}
exit 3
