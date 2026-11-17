# Generate EXACT production media graph with synthetic credentials, safely.
# Extract only the graph-construction block; never dot-source Record.ps1,
# which would contact a real camera. The same tokens are sent to gst-launch.
param(
  [Parameter(Mandatory=$true)][string]$OutputPath,
  [bool]$SeiFilter = $true,
  [bool]$H264InputGuard = $true,
  [bool]$AudioTsGuard = $true,
  [bool]$DtsGuard = $true
)
$ErrorActionPreference='Stop'
$source=[IO.File]::ReadAllText((Join-Path (Split-Path -Parent $PSScriptRoot) 'Record.ps1'))
$begin=$source.IndexOf('$pipeline = New-Object', [StringComparison]::Ordinal)
$stop=$source.IndexOf('# Never echo the pipeline:', $begin, [StringComparison]::Ordinal)
if ($begin -lt 0 -or $stop -lt 0) { throw 'Production pipeline generator boundary missing' }
$snippet=$source.Substring($begin,$stop-$begin)
if ($snippet -notmatch "Add-Input 'cam2'") { throw 'Telephoto graph missing' }
# Import the real production Gst-Value helper from an AST without executing
# configuration, retrieving real credentials, or attempting RTSP.
$tokens=$null; $parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$parseErrors)
if (@($parseErrors).Count) { throw 'Recorder failed PowerShell syntax parser' }
$node=$ast.Find({ param($n)
  ($n -is [Management.Automation.Language.FunctionDefinitionAst]) -and
  ($n.Name -eq 'Gst-Value')
},$true)
if (-not $node) { throw 'Production Gst-Value missing' }
. ([scriptblock]::Create($node.Extent.Text))
$script:useDtsGuard=$DtsGuard
$script:useH264InputGuard=$H264InputGuard
$script:useSeiAuFilter=$SeiFilter
$script:useAudioTimestampGuard=$AudioTsGuard
$script:rtspDriftArgs=@('max-ts-offset-adjustment=1000000')
$script:videoRateArgs=@('videorate','max-duplication-time=300000000','skip-to-first=true')
$pattern='C:\synthetic\recording_%05d.mp4'
$wideURL='rtsp://192.0.2.10:554/stream1'
$teleURL='rtsp://192.0.2.10:554/stream6'
$cameraPass='SYNTHETIC_NOT_A_PASSWORD'
$userName='synthetic'
$decoder=@('avdec_h264')
$audioCaps='audio/x-raw,format=F32LE,layout=interleaved,rate=48000,channels=1'
$audioEncoder=@('avenc_aac','bitrate=192000')
. ([scriptblock]::Create($snippet))
if (@($pipeline | Where-Object { $_ -eq 'c545dseifilter' }).Count -ne $(if($SeiFilter){2}else{0})) {
   throw 'Unexpected SEI filter branch count'
}
# Newline-separated original arguments are fed to native gst_parse_launchv.
# Never write any real secrets (the only values here are dummy).
[IO.File]::WriteAllLines($OutputPath,[string[]]$pipeline.ToArray(),
    (New-Object Text.UTF8Encoding($false)))
Write-Host ('Synthetic production graph emitted: tokens=' + $pipeline.Count +
    ' sei=' + $SeiFilter + ' h264=' + $H264InputGuard +
    ' audio=' + $AudioTsGuard + ' dts=' + $DtsGuard)
