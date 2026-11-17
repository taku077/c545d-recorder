using System;
using System.IO;
using System.Threading;
using System.Windows.Forms;

namespace C545D.Recorder.Launcher
{
    internal static class Program
    {
        [STAThread]
        private static void Main(string[] args)
        {
            bool smoke = args.Length == 1 && args[0] == "--smoke";
            string folder = AppDomain.CurrentDomain.BaseDirectory;
            string[] required = {
                "C545D_SettingsBridge.ps1", "Record.ps1", "RecordGUIWorker.ps1",
                "SegmentNamer.ps1", "SegmentNamerWorker.ps1", "CommonSettings.ps1",
                "RecoverPending.ps1", "C545D_App.ps1", "C545D_Start.vbs"
            };
            foreach (string name in required)
            {
                if (!File.Exists(Path.Combine(folder, name)))
                {
                    MessageBox.Show("必要なファイルがありません: " + name +
                        Environment.NewLine + "ZIPをすべて展開してください。",
                        "C545D 録画アプリ", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
            }
            bool owner = false;
            using (var gate = new Mutex(true, @"Local\C545D_Recorder_Native_UI", out owner))
            {
                if (!owner)
                {
                    MessageBox.Show("新しいC545D録画画面は既に起動しています。",
                        "C545D 録画アプリ", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return;
                }
                try
                {
                    // Inherited by the hidden private-console recording worker.
                    // Do not pass environment variables through ShellExecuteEx.
                    Environment.SetEnvironmentVariable("C545D_VIDEO_DECODER", "avdec");
                    Application.EnableVisualStyles();
                    Application.SetCompatibleTextRenderingDefault(false);
                    // Stage 2: native C# WinForms controller. The tested PS/GStreamer
                    // media worker remains unchanged and runs in its own console.
                    using (var form = new RecorderForm(smoke))
                        Application.Run(form);
                }
                catch (Exception ex)
                {
                    MessageBox.Show("C545D録画アプリを起動できませんでした。" +
                        Environment.NewLine + ex.Message, "C545D 録画アプリ",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                finally
                {
                    gate.ReleaseMutex();
                }
            }
        }
    }
}
