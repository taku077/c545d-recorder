# CI-only private native controller mirror. Never packaged or installed.
param([Parameter(Mandatory=$true)][string]$Stage)
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
   [IO.File]::ReadAllText((Join-Path $Stage '.c545d-ci-owned')) -cne 'CI_MIRROR_ONLY_NOT_FOR_EXECUTION' -or
   [IO.Path]::GetFullPath($Stage).TrimEnd('\') -notmatch '\\c545d-ci-production-mirror-[a-f0-9]{32}$' -or
   [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Stage).TrimEnd('\')) -ine [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')){
  throw 'NATIVE_CI_ONLY'
}
$src=(Resolve-Path 'src/C545D.Launcher').Path
$original=[IO.File]::ReadAllText((Join-Path $src 'RecorderForm.cs'))
$rootAnchor='Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "C545D_GStreamer"'
$rootReplacement='Environment.GetEnvironmentVariable("LOCALAPPDATA"), "C545D_GStreamer"'
$shownAnchor='status.Text = "設定を確認し、「録画開始」を押してください。";'
$hook=@'
status.Text = "設定を確認し、「録画開始」を押してください。";
                var ciClock = Stopwatch.StartNew();
                int ciPhase = 0;
                var ciTimer = new System.Windows.Forms.Timer { Interval = 200 };
                ciTimer.Tick += (cs, ce) => {
                    try {
                        if (ciClock.Elapsed.TotalSeconds > 155) throw new Exception("TIMEOUT");
                        if (Environment.GetEnvironmentVariable("GITHUB_ACTIONS") != "true" ||
                            Environment.GetEnvironmentVariable("RUNNER_OS") != "Windows" ||
                            File.ReadAllText(Path.Combine(appDir, ".c545d-ci-owned")) != "CI_MIRROR_ONLY_NOT_FOR_EXECUTION" ||
                            Root != Path.Combine(appDir.TrimEnd('\\'), "ci-localappdata", "C545D_GStreamer"))
                            throw new Exception("GUARD");
                        if (ciPhase == 0) {
                            if (ip.Text != "127.0.0.1" || user.Text != "CI_SYNTHETIC_NO_AUTH" ||
                                output.Text != Path.Combine(appDir.TrimEnd('\\'), "private-output") ||
                                !start.Enabled) throw new Exception("SETTINGS");
                            seiFilter.Checked = false;
                            start.PerformClick();
                            if (!Alive(worker) || !File.Exists(namerReadyFile)) throw new Exception("START");
                            ciPhase = 1;
                            File.WriteAllText(Path.Combine(appDir, "ci-gui-session"), sessionId + "," + worker.Id);
                        } else if (ciPhase == 1 && File.Exists(Path.Combine(appDir, "ci-gui-request-stop"))) {
                            if (!File.Exists(readyFile) || !stop.Enabled) throw new Exception("NOT_READY");
                            stop.PerformClick();
                            if (!stopRequested || stopSignalFailed || !File.Exists(stopFile)) throw new Exception("STOP");
                            File.WriteAllText(Path.Combine(appDir, "ci-gui-stop-ok"), "STOP_MARKER_AND_GUI_CTRL_C");
                            ciPhase = 2;
                        } else if (ciPhase == 2 && File.Exists(Path.Combine(appDir, "ci-gui-allow-quit")) && !Alive(worker)) {
                            File.WriteAllText(Path.Combine(appDir, "ci-gui-quit-ok"), "WINFORMS_QUIT_CLICKED");
                            ciTimer.Stop();
                            ciTimer.Dispose();
                            quit.PerformClick();
                            ciPhase = 3;
                        }
                    } catch {
                        File.WriteAllText(Path.Combine(appDir, "ci-gui-failure"), "CI_GUI_NATIVE_PHASE_" + (ciPhase == 0 ? "START" : ciPhase == 1 ? "STOP" : "QUIT"));
                        ciTimer.Stop();
                        ciTimer.Dispose();
                    }
                };
                ciTimer.Start();
'@
foreach($anchor in @($rootAnchor,$shownAnchor)){
  if([regex]::Matches($original,[regex]::Escape($anchor)).Count -ne 1){throw 'NATIVE_CI_ANCHOR'}
}
$mirror=$original.Replace($rootAnchor,$rootReplacement).Replace($shownAnchor,$hook)
if($mirror.Replace($hook,$shownAnchor).Replace($rootReplacement,$rootAnchor) -cne $original){throw 'NATIVE_CI_ROUNDTRIP'}
$code=Join-Path $Stage 'RecorderForm.CI_ONLY.cs'
[IO.File]::WriteAllText($code,$mirror,[Text.UTF8Encoding]::new($true))
$csc=Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$out=Join-Path $Stage 'C545D_Native_CI_ONLY.exe'
& $csc /nologo /target:winexe /platform:x64 /optimize+ /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Web.Extensions.dll ("/out:"+$out) (Join-Path $src 'Program.cs') $code *> $null
if($LASTEXITCODE -ne 0 -or -not(Test-Path -LiteralPath $out -PathType Leaf)){throw 'NATIVE_CI_COMPILE'}
Write-Host 'C545D_NATIVE_MIRROR_BUILD,root_redirected=1,button_hook=1,roundtrip=1,packaged_binary=0,ci_only=1'
