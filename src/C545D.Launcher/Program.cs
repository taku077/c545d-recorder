// Stage 1 EXE: a minimal WinForms-capable launcher for the existing,
// well-tested PowerShell UI. The recording pipeline and Ctrl+C/EOS
// shutdown logic remain in the original scripts, unchanged.
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace C545D.Recorder.Launcher
{
    internal static class Program
    {
        private static readonly string[] RequiredFiles = new[]
        {
            "C545D_App.ps1",
            "Record.ps1",
            "RecordGUIWorker.ps1",
            "SegmentNamer.ps1",
            "SegmentNamerWorker.ps1",
            "CommonSettings.ps1",
            "RecoverPending.ps1",
            "C545D_Start.vbs",
            "README.txt"
        };

        [STAThread]
        private static void Main()
        {
            try
            {
                string applicationFolder = AppDomain.CurrentDomain.BaseDirectory;
                foreach (string fileName in RequiredFiles)
                {
                    if (!File.Exists(Path.Combine(applicationFolder, fileName)))
                    {
                        ShowError("必要なファイルがありません: " + fileName +
                                  Environment.NewLine +
                                  "ZIPを「すべて展開」してからEXEを起動してください。");
                        return;
                    }
                }

                // The x64 build launches 64-bit Windows PowerShell 5.1.
                // This preserves compatibility with the existing STA WinForms
                // controller, saved DPAPI credentials and gst-launch workers.
                string powershellExe = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.Windows),
                    "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
                if (!File.Exists(powershellExe))
                {
                    ShowError("Windows PowerShell 5.1が見つかりません。");
                    return;
                }

                string appScript = Path.Combine(applicationFolder, "C545D_App.ps1");
                var startInfo = new ProcessStartInfo
                {
                    FileName = powershellExe,
                    Arguments = "-NoLogo -NoProfile -STA -ExecutionPolicy Bypass " +
                                "-WindowStyle Hidden -File " + Quote(appScript),
                    WorkingDirectory = applicationFolder,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                };

                // Same environment preference as the previous C545D_Start.vbs.
                // It is scoped to the child process, not global Windows settings.
                startInfo.EnvironmentVariables["C545D_VIDEO_DECODER"] = "avdec";

                // We deliberately do not remain attached to the child or
                // terminate it on launcher exit: the original GUI handles
                // stop markers and graceful GStreamer -e finalization.
                using (Process child = Process.Start(startInfo))
                {
                    if (child == null)
                    {
                        ShowError("録画画面の起動に失敗しました。");
                    }
                }
            }
            catch (Exception ex)
            {
                ShowError("C545D録画アプリを起動できませんでした。" +
                          Environment.NewLine + ex.Message);
            }
        }

        private static string Quote(string path)
        {
            // Windows file and directory names cannot contain double quotes.
            return "\"" + path + "\"";
        }

        private static void ShowError(string message)
        {
            MessageBox.Show(message, "C545D 録画アプリ",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
