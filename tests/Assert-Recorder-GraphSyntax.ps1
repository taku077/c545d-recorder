# GStreamer input graph test: execute ONLY pure Add-Input and separator-guard
# function ASTs from Record.ps1. Never dot-source Record.ps1 or connect camera.
# Covers input guard true/false × SEI filter true/false × audio true/false.
$ErrorActionPreference='Stop'
$root = Split-Path -Parent $PSScriptRoot
$path = Join-Path $root 'Record.ps1'
$tokens=$null; $parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile(
    $path,[ref]$tokens,[ref]$parseErrors)
if (@($parseErrors).Count -gt 0) { throw 'Record.ps1 source parsing failed' }
function Import-PureFunction([string]$name) {
    $fn=$ast.Find({
       param($n)
       ($n -is [System.Management.Automation.Language.FunctionDefinitionAst]) -and
       ($n.Name -eq $name)
    },$true)
    if (-not $fn) { throw "Missing pipeline function $name" }
    . ([scriptblock]::Create($fn.Extent.Text))
    # Dot-sourcing inside this helper creates only a local function; export
    # script block into the test scope for later direct invocation.
    return $fn.Extent.Text
}
foreach ($name in @('Add-Input','Assert-C545DPipelineSeparators')) {
    . ([scriptblock]::Create((Import-PureFunction $name)))
}
# Test-only shims: same token addition as the actual application, but
# fake credentials and RTSP URLs, no real process or filesystem side-effects.
function Add-Gst([string[]]$parts) {
    foreach($part in $parts){ [void]$script:pipeline.Add($part) }
}
function Gst-Value([string]$value) {
    return '"' + $value.Replace('\','\\').Replace('"','\"') + '"'
}
$script:userName='synthetic';$script:cameraPass='NOT_REAL';
$script:decoder=@('avdec_h264')
$script:audioCaps='audio/x-raw,rate=48000,channels=1'
$script:audioEncoder=@('avenc_aac','bitrate=192000')
$script:rtspDriftArgs=@()
$script:videoRateArgs=@('videorate')
foreach($inputGuard in @($false,$true)){
 foreach($sei in @($false,$true)){
  foreach($audio in @($false,$true)){
   $script:pipeline=New-Object 'System.Collections.Generic.List[string]'
   $script:useH264InputGuard=$inputGuard
   $script:useSeiAuFilter=$sei
   $script:useAudioTimestampGuard=$audio
   Add-Input 'cam1' 'rtsp://192.0.2.10:554/stream1' 0
   Add-Input 'cam2' 'rtsp://192.0.2.10:554/stream6' 1
   Assert-C545DPipelineSeparators $script:pipeline.ToArray()
   $text=$script:pipeline.ToArray()
   $num=@($text | Where-Object {$_ -eq 'c545dseifilter'}).Count
   $expected=if ($sei) {2} else {0}
   if ($num -ne $expected) { throw "Expected $expected filters, saw $num" }
   if ($sei) {
      $indices=@(for($i=0;$i -lt $text.Length;$i++) {
          if($text[$i] -eq 'c545dseifilter') {$i}
      })
      foreach($i in $indices) {
          if($i -lt 3 -or $i -ge $text.Length-2 -or
             $text[$i-1] -ne '!' -or
             $text[$i-2] -ne 'video/x-h264,stream-format=byte-stream,alignment=au' -or
             $text[$i+1] -ne '!' -or
             $text[$i+2] -ne 'avdec_h264') {
             throw 'SEI filter not directly after Annex B AU caps or before decoder'
          }
      }
   }
   Write-Host ("PASS inputGuard=$inputGuard sei=$sei audio=$audio")
  }
 }
}
# Negative control: prove the validator actually rejects the prior bug.
$broken=@('h264parse','!','!','video/x-h264,stream-format=byte-stream,alignment=au')
$threw=$false
try { Assert-C545DPipelineSeparators $broken } catch { $threw=$true }
if (-not $threw) { throw 'Validator did not catch the old double-! regression' }
Write-Host 'PASS double separator fails closed without camera or credentials'
