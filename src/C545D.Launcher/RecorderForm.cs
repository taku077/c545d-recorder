using System;
using System.ComponentModel;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace C545D.Recorder.Launcher
{
    internal sealed class RecorderForm : Form
    {
        private static readonly string Root = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "C545D_GStreamer");
        private static readonly string Control = Path.Combine(Root, "Control");
        private static readonly string Logs = Path.Combine(Root, "Logs");
        private readonly string appDir = AppDomain.CurrentDomain.BaseDirectory;
        private readonly string powershell = Path.Combine(Environment.GetFolderPath(
            Environment.SpecialFolder.Windows), @"System32\WindowsPowerShell\v1.0\powershell.exe");
        private readonly bool smoke;
        private readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
        private TextBox ip, user, password, output;
        private Label passwordStatus, status, elapsed, memory;
        private Button start, stop, save, browse, emergency, quit;
        private NotifyIcon tray;
        private Process worker, namer, emergencyTask;
        private string sessionId = "", stopFile = "", readyFile = "";
        private string namerFolder = "", namerStopFile = "", namerReadyFile = "";
        private bool stopRequested, stopSignalFailed, emergencyRequested, quitAfterStop, allowExit;
        private bool noticed15, noticed60;
        private DateTime startedAt, stopAt;
        private int ticks;
        private string lastGstIds = "";
        private DateTime lastGstAt;
        private double lastGstCpu;

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool FreeConsole();
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool AttachConsole(uint processId);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GenerateConsoleCtrlEvent(uint ctrlEvent, uint processGroupId);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);

        public RecorderForm(bool smokeMode)
        {
            smoke = smokeMode;
            Text = "C545D 録画アプリ — C# WinForms";
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(730, 600);
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            Font = new Font("Meiryo UI", 9f);
            BackColor = Color.FromArgb(248, 250, 252);
            BuildControls();
            timer.Interval = 1000;
            timer.Tick += (s, e) => Tick();
            FormClosing += Closing;
            FormClosed += (s, e) => Cleanup();
            Resize += (s, e) => { if (WindowState == FormWindowState.Minimized) Hide(); };
            Shown += (s, e) => {
                if (smoke)
                {
                    string p = Environment.GetEnvironmentVariable("C545D_NATIVE_SMOKE_OUTPUT");
                    if (!string.IsNullOrEmpty(p))
                        File.WriteAllText(p, "PASS NATIVE WINFORMS", Encoding.UTF8);
                    BeginInvoke((Action)(() => { allowExit = true; Close(); }));
                    return;
                }
                ReadSettings();
                StartNamer();
                timer.Start();
                status.Text = "設定を確認し、「録画開始」を押してください。";
                RefreshButtons();
            };
        }

        private Label L(string text, int x, int y, int w, int h = 26)
        {
            var l = new Label { Text = text, Location = new Point(x, y),
                Size = new Size(w, h), TextAlign = ContentAlignment.MiddleLeft };
            Controls.Add(l);
            return l;
        }
        private TextBox T(int x, int y, int w, bool secret = false)
        {
            var t = new TextBox { Location = new Point(x, y), Width = w,
                UseSystemPasswordChar = secret };
            Controls.Add(t);
            return t;
        }
        private Button B(string text, int x, int y, int w, int h, Action handler)
        {
            var b = new Button { Text = text, Location = new Point(x, y),
                Size = new Size(w, h), FlatStyle = FlatStyle.System };
            b.Click += (s, e) => handler();
            Controls.Add(b);
            return b;
        }
        private void BuildControls()
        {
            L("Tapo C545D  2画面録画", 22, 12, 640, 42).Font =
                new Font("Meiryo UI", 16f, FontStyle.Bold);
            L("広角＋望遠を横並びでMP4保存  |  音声1系統  |  1時間分割", 24, 57, 680);
            L("カメラIPv4", 24, 112, 125);
            ip = T(160, 110, 225);
            L("アカウント", 400, 112, 96);
            user = T(500, 110, 200);
            L("パスワード", 24, 160, 125);
            password = T(160, 158, 225, true);
            passwordStatus = L("", 398, 160, 308);
            passwordStatus.Font = new Font("Meiryo UI", 8);
            L("MP4保存先", 24, 210, 125);
            output = T(160, 208, 420);
            browse = B("参照…", 590, 205, 110, 34, Browse);
            save = B("設定を保存", 160, 257, 170, 38, () => SaveWithError());
            start = B("● 録画開始", 24, 322, 215, 48, StartRecording);
            stop = B("■ 録画停止", 251, 322, 215, 48, RequestStop);
            B("保存先を開く", 478, 322, 222, 48, () => OpenFolder(output.Text));
            status = L("準備中", 24, 395, 680, 35);
            status.ForeColor = Color.FromArgb(28, 81, 123);
            elapsed = L("録画時間：—", 24, 432, 235);
            memory = L("GStreamer メモリ：—", 255, 432, 285);
            memory.Font = new Font("Meiryo UI", 8);
            B("ログを開く", 546, 426, 154, 34, () => OpenFolder(Logs));
            emergency = B("緊急停止（最後のMP4破損の可能性）", 24, 482, 445, 42, EmergencyStop);
            emergency.ForeColor = Color.DarkRed;
            quit = B("アプリを終了", 480, 482, 220, 42, RequestExit);
            var foot = L("最小化すると通知領域に格納します。映像プレビューなし・軽量動作。", 24, 546, 690);
            foot.Font = new Font("Meiryo UI", 8);
            tray = new NotifyIcon { Icon = SystemIcons.Application,
                Text = "C545D 録画アプリ", Visible = !smoke };
            var menu = new ContextMenuStrip();
            menu.Items.Add("ウィンドウを表示", null, (s, e) => ShowWindow());
            menu.Items.Add("録画停止（MP4確定）", null, (s, e) => RequestStop());
            menu.Items.Add("緊急停止（最終MP4破損の危険）", null,
                (s, e) => { ShowWindow(); EmergencyStop(); });
            menu.Items.Add("アプリを終了", null, (s, e) => { ShowWindow(); RequestExit(); });
            tray.ContextMenuStrip = menu;
            tray.DoubleClick += (s, e) => ShowWindow();
            RefreshButtons();
        }
        private void ShowWindow()
        {
            Show(); WindowState = FormWindowState.Normal; Activate();
        }
        private void Error(string message)
        {
            MessageBox.Show(this, message, "C545D 録画アプリ",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        private void Browse()
        {
            using (var d = new FolderBrowserDialog())
            {
                d.Description = "MP4を直接保存するフォルダーを選択してください。";
                d.ShowNewFolderButton = true;
                if (Directory.Exists(output.Text)) d.SelectedPath = output.Text;
                if (d.ShowDialog(this) == DialogResult.OK) output.Text = d.SelectedPath;
            }
        }
        private void OpenFolder(string path)
        {
            if (!Directory.Exists(path)) { Error("フォルダーが存在しません。"); return; }
            Process.Start("explorer.exe", "\"" + path + "\"");
        }
        private void ReadSettings()
        {
            try
            {
                string config = Path.Combine(Root, "settings.json");
                string secret = Path.Combine(Root, "camera_password.dpapi");
                if (File.Exists(config) && File.Exists(secret))
                {
                    var dict = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(
                        File.ReadAllText(config, Encoding.UTF8));
                    ip.Text = Convert.ToString(dict["camera_ip"]);
                    user.Text = Convert.ToString(dict["camera_user"]);
                    output.Text = Convert.ToString(dict["output_folder"]);
                    password.Clear();
                    passwordStatus.Text = "保存済み：空欄なら変更しません";
                    return;
                }
            }
            catch { passwordStatus.Text = "設定が読めません。確認してください。"; }
            output.Text = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            if (string.IsNullOrWhiteSpace(passwordStatus.Text))
                passwordStatus.Text = "初回はパスワードを入力してください";
        }
        private void SaveSettings()
        {
            IPAddress address;
            if (!IPAddress.TryParse(ip.Text.Trim(), out address) ||
                address.AddressFamily != AddressFamily.InterNetwork)
                throw new InvalidOperationException("カメラのIPv4アドレスを確認してください。");
            if (string.IsNullOrWhiteSpace(user.Text))
                throw new InvalidOperationException("カメラのユーザー名を入力してください。");
            if (!Directory.Exists(output.Text.Trim()))
                throw new InvalidOperationException("保存先フォルダーが存在しません。");
            if (string.IsNullOrEmpty(password.Text) &&
                !File.Exists(Path.Combine(Root, "camera_password.dpapi")))
                throw new InvalidOperationException("初回はカメラのパスワードを入力してください。");

            // Password is sent ONLY over anonymous stdin, not in command line,
            // logs, on disk as plaintext, or in GitHub. PowerShell's established
            // DPAPI ConvertFrom-SecureString format is kept by SettingsBridge.
            var payload = new Dictionary<string, string> {
                { "camera_ip", ip.Text.Trim() }, { "camera_user", user.Text.Trim() },
                { "output_folder", output.Text.Trim() }, { "new_password", password.Text }
            };
            var psi = new ProcessStartInfo {
                FileName = powershell, WorkingDirectory = appDir,
                Arguments = "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File " +
                    Quote(Path.Combine(appDir, "C545D_SettingsBridge.ps1")),
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardInput = true, RedirectStandardOutput = true,
                RedirectStandardError = true
            };
            using (var helper = Process.Start(psi))
            {
                if (helper == null) throw new InvalidOperationException("設定処理を起動できません。");
                helper.StandardInput.Write(Convert.ToBase64String(Encoding.UTF8.GetBytes(
                    new JavaScriptSerializer().Serialize(payload))));
                helper.StandardInput.Close();
                if (!helper.WaitForExit(15000))
                {
                    try { helper.Kill(); } catch { }
                    throw new InvalidOperationException("設定保存がタイムアウトしました。");
                }
                if (helper.ExitCode != 0)
                    throw new InvalidOperationException("設定を保存できませんでした。保存先の書込権限と既存パスワードを確認してください。");
            }
            password.Clear();
            passwordStatus.Text = "保存済み：空欄なら変更しません";
            status.Text = "設定を保存しました。録画開始できます。";
        }
        private bool SaveWithError()
        {
            try { SaveSettings(); return true; }
            catch (Exception ex) { Error(ex.Message); return false; }
        }
        private static string Quote(string value) { return "\"" + value + "\""; }
        private Process StartScript(string script, string arguments, bool withConsole)
        {
            // .NET Framework 4.8 ignores WindowStyle.Hidden when
            // UseShellExecute=false. The recorder needs a *real* private console
            // so AttachConsole/GenerateConsoleCtrlEvent can finalize MP4 via EOS.
            // ShellExecuteEx honors SW_HIDE while retaining that private console.
            // Stage-1 Start-Process -WindowStyle Hidden used the same approach.
            var psi = new ProcessStartInfo {
                FileName = powershell,
                Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File " +
                    Quote(Path.Combine(appDir, script)) + " " + arguments,
                WorkingDirectory = appDir,
                UseShellExecute = withConsole,
                CreateNoWindow = !withConsole,
                WindowStyle = ProcessWindowStyle.Hidden
            };
            if (!withConsole) psi.EnvironmentVariables["C545D_VIDEO_DECODER"] = "avdec";
            // The console worker inherits C545D_VIDEO_DECODER=avdec from this
            // WinExe process, which is set before launching the WinForms UI.
            return Process.Start(psi);
        }
        private bool Alive(Process p)
        {
            if (p == null) return false;
            try { return !p.HasExited; } catch { return false; }
        }
        private void RefreshButtons()
        {
            bool active = Alive(worker);
            ip.Enabled = user.Enabled = password.Enabled = output.Enabled = !active;
            browse.Enabled = save.Enabled = start.Enabled = !active;
            stop.Enabled = active && (!stopRequested || stopSignalFailed);
            stop.Text = stopSignalFailed ? "■ 停止通知を再試行" : "■ 録画停止";
            emergency.Visible = active && stopRequested;
            emergency.Enabled = active && stopRequested && !emergencyRequested;
        }
        private void Log(string message)
        {
            try
            {
                Directory.CreateDirectory(Logs);
                File.AppendAllText(Path.Combine(Logs, "Stop_Control.log"),
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") +
                    " [Native GUI " + Process.GetCurrentProcess().Id + "] [session " +
                    (sessionId == "" ? "-" : sessionId) + "] " + message + Environment.NewLine,
                    Encoding.UTF8);
            }
            catch { }
        }
        private void StartRecording()
        {
            if (Alive(worker)) return;
            try
            {
                // Avoid opening a second RTSP session against C545D while an
                // old PowerShell/OBS gst-launch worker might still be active.
                if (Process.GetProcessesByName("gst-launch-1.0").Length != 0)
                {
                    Error("gst-launch-1.0が既に起動しています。既存録画を正常停止してから開始してください。");
                    return;
                }
                SaveSettings();
                StartNamer();
                WaitNamerReady();
                Directory.CreateDirectory(Control);
                sessionId = Guid.NewGuid().ToString("N");
                stopFile = Path.Combine(Control, "session_" + sessionId + ".stop");
                readyFile = Path.Combine(Control, "session_" + sessionId + ".ready");
                worker = StartScript("RecordGUIWorker.ps1", "-SessionId " + sessionId, true);
                if (worker == null) throw new InvalidOperationException("録画プロセスを起動できません。");
                startedAt = DateTime.Now;
                stopRequested = stopSignalFailed = emergencyRequested = false;
                noticed15 = noticed60 = quitAfterStop = false;
                Log("Worker launched PID=" + worker.Id);
                status.Text = "録画プロセスを起動しました。接続中…";
            }
            catch (Exception ex)
            {
                if (!Alive(worker)) ClearSessionMarkers();
                Error(ex.Message);
            }
            RefreshButtons();
        }
        private void WaitNamerReady()
        {
            // Small bounded startup wait, only once per start; no per-frame polling.
            for (int i = 0; i < 50; i++)
            {
                if (!string.IsNullOrEmpty(namerReadyFile) && File.Exists(namerReadyFile)) return;
                if (namer != null && !Alive(namer)) break;
                System.Threading.Thread.Sleep(100);
            }
            Log("WARNING: optional rename watcher not ready; recording still allowed.");
        }
        private void StartNamer()
        {
            string folder = output.Text.Trim();
            if (!Directory.Exists(folder)) return;
            if (Alive(namer) && string.Equals(namerFolder, folder,
                StringComparison.OrdinalIgnoreCase)) return;
            StopNamer();
            try
            {
                Directory.CreateDirectory(Control);
                string id = Guid.NewGuid().ToString("N");
                namerReadyFile = Path.Combine(Control, "namer_" + id + ".ready");
                namerStopFile = Path.Combine(Control, "namer_" + id + ".stop");
                namer = StartScript("SegmentNamerWorker.ps1",
                    "-OutputDirectory " + Quote(folder) + " -OwnerProcessId " +
                    Process.GetCurrentProcess().Id + " -ReadyFile " +
                    Quote(namerReadyFile) + " -StopFile " + Quote(namerStopFile), false);
                namerFolder = folder;
                if (namer != null) Log("Namer started PID=" + namer.Id);
            }
            catch (Exception ex)
            {
                namer = null; Log("Optional namer failed: " + ex.GetType().Name);
            }
        }
        private void StopNamer()
        {
            if (!string.IsNullOrEmpty(namerStopFile))
                try { File.WriteAllText(namerStopFile, DateTime.Now.ToString("o")); } catch { }
            if (namer != null) { namer.Dispose(); namer = null; }
            namerReadyFile = namerStopFile = namerFolder = "";
        }
        private void ClearSessionMarkers()
        {
            foreach (var path in new[] { stopFile, readyFile })
                if (!string.IsNullOrEmpty(path))
                    try { File.Delete(path); } catch { }
            sessionId = stopFile = readyFile = "";
        }
        private void RequestStop()
        {
            if (!Alive(worker) || (stopRequested && !stopSignalFailed)) return;
            bool again = stopRequested;
            stopRequested = true;
            if (!again) stopAt = DateTime.Now;
            Log("Stop requested, worker=" + worker.Id + " retry=" + again);
            try
            {
                if (string.IsNullOrEmpty(stopFile))
                    throw new IOException("停止要求ファイルのパスがありません。");
                File.WriteAllText(stopFile, DateTime.Now.ToString("o"));
                Log("Stop marker written.");
            }
            catch (Exception ex)
            {
                stopSignalFailed = true;
                Error("停止要求を保存できません。Ctrl+Cは送信していません。" +
                    Environment.NewLine + ex.Message);
                RefreshButtons(); return;
            }
            status.Text = "停止要求を記録しました。MP4確定を待機しています…";
            if (string.IsNullOrEmpty(readyFile) || !File.Exists(readyFile))
            {
                status.Text = "録画準備中のため停止を予約しました。安全に終了します…";
                Log("Worker not ready; durable stop marker will prevent recording.");
                RefreshButtons(); return;
            }
            bool attached = false;
            try
            {
                FreeConsole();
                attached = AttachConsole((uint)worker.Id);
                if (!attached)
                    throw new Win32Exception(Marshal.GetLastWin32Error(),
                        "ワーカーのコンソールに接続できません。");
                if (!SetConsoleCtrlHandler(IntPtr.Zero, true))
                    throw new Win32Exception(Marshal.GetLastWin32Error(),
                        "GUI側のCtrl+C保護ができません。");
                if (!GenerateConsoleCtrlEvent(0, 0))
                    throw new Win32Exception(Marshal.GetLastWin32Error(),
                        "Ctrl+Cを送信できません。");
                stopSignalFailed = false;
                status.Text = "終了通知を送信しました。MP4確定処理中…";
                Log("CTRL_C_EVENT delivered. Waiting for -e EOS.");
            }
            catch (Exception ex)
            {
                stopSignalFailed = true;
                status.Text = "終了通知に問題があります。停止要求は保持しています。";
                Log("ERROR stop signal: " + ex.GetType().Name);
                Error("停止要求は記録済みですが、終了通知に失敗しました。強制終了はしていません。" +
                      Environment.NewLine + ex.Message);
            }
            finally
            {
                if (attached) FreeConsole();
                SetConsoleCtrlHandler(IntPtr.Zero, false);
                RefreshButtons();
            }
        }
        private void EmergencyStop()
        {
            if (!Alive(worker)) return;
            if (!stopRequested)
            {
                MessageBox.Show(this, "まず通常の録画停止を試してください。");
                return;
            }
            if (emergencyRequested) return;
            if (MessageBox.Show(this,
                "録画セッションを強制終了すると最後のMP4が破損する可能性があります。" +
                Environment.NewLine + "通常停止できない場合の最終手段です。実行しますか？",
                "緊急停止の確認", MessageBoxButtons.YesNo, MessageBoxIcon.Warning,
                MessageBoxDefaultButton.Button2) != DialogResult.Yes) return;
            try
            {
                if (!string.IsNullOrEmpty(stopFile))
                    try { File.WriteAllText(stopFile, DateTime.Now.ToString("o")); } catch { }
                var psi = new ProcessStartInfo {
                    FileName = Path.Combine(Environment.GetFolderPath(
                        Environment.SpecialFolder.Windows), @"System32\taskkill.exe"),
                    Arguments = "/PID " + worker.Id + " /T /F", CreateNoWindow = true,
                    UseShellExecute = false, WindowStyle = ProcessWindowStyle.Hidden
                };
                emergencyTask = Process.Start(psi);
                emergencyRequested = true;
                status.Text = "緊急停止を要求しました。最終MP4を確認してください。";
                Log("User confirmed emergency taskkill for worker " + worker.Id);
            }
            catch (Exception ex) { emergencyRequested = false; Error(ex.Message); }
            RefreshButtons();
        }
        private void RequestExit()
        {
            if (Alive(worker))
            {
                if (MessageBox.Show(this, "録画を正常停止し、MP4確定後にアプリを終了しますか？",
                    "録画中の終了", MessageBoxButtons.YesNo, MessageBoxIcon.Question,
                    MessageBoxDefaultButton.Button2) == DialogResult.Yes)
                {
                    quitAfterStop = true;
                    RequestStop();
                }
                return;
            }
            allowExit = true; Close();
        }
        private void Closing(object sender, FormClosingEventArgs e)
        {
            if (!allowExit && Alive(worker))
            {
                e.Cancel = true; ShowWindow(); RequestExit();
            }
        }
        private void Tick()
        {
            ticks++;
            if (ticks % 30 == 0) UpdateHealth();
            if (ticks % 10 == 0) StartNamer();
            if (emergencyTask != null && !Alive(emergencyTask))
            {
                int ec = emergencyTask.ExitCode;
                Log("Emergency command exit=" + ec);
                emergencyTask.Dispose(); emergencyTask = null;
                if (Alive(worker) && ec != 0)
                {
                    emergencyRequested = false;
                    status.Text = "緊急停止に失敗しました。ログをご確認ください。";
                }
            }
            if (worker != null && Alive(worker))
            {
                TimeSpan t = DateTime.Now - startedAt;
                elapsed.Text = string.Format("起動経過：{0:00}:{1:00}:{2:00}",
                    (int)t.TotalHours, t.Minutes, t.Seconds);
                if (stopRequested)
                {
                    TimeSpan s = DateTime.Now - stopAt;
                    if (s.TotalSeconds >= 60)
                    {
                        status.Text = "通常停止が60秒以上続いています。Ctrl+Cを重ねて送らないでください。";
                        if (!noticed60) { noticed60 = true; Log("WARNING: EOS >60s"); }
                    }
                    else if (s.TotalSeconds >= 15)
                    {
                        status.Text = "MP4確定待ち（15秒以上）。再度Ctrl+Cを送らないでください。";
                        if (!noticed15) { noticed15 = true; Log("WARNING: EOS >15s"); }
                    }
                }
                else status.Text = "録画プロセス実行中（接続状況はログで確認）";
                RefreshButtons();
            }
            else if (worker != null)
            {
                int ec = -1;
                try { ec = worker.ExitCode; } catch { }
                worker.Dispose(); worker = null;
                bool stopped = stopRequested;
                Log("Worker exited, code=" + ec + " stopped=" + stopped);
                stopRequested = stopSignalFailed = emergencyRequested = false;
                ClearSessionMarkers();
                status.Text = stopped ?
                    "録画処理が終了しました。最後のMP4の再生可否をご確認ください。" :
                    "録画プロセスが終了しました（終了コード " + ec + "）。ログを確認してください。";
                RefreshButtons();
                if (quitAfterStop)
                {
                    quitAfterStop = false; allowExit = true; Close();
                }
            }
        }
        private void UpdateHealth()
        {
            var procs = Process.GetProcessesByName("gst-launch-1.0");
            try
            {
                if (procs.Length == 0) { memory.Text = "GStreamer メモリ：—"; lastGstIds = ""; return; }
                long ws = 0, priv = 0;
                double cpu = 0;
                var ids = new List<int>();
                foreach (Process p in procs)
                {
                    try
                    {
                        p.Refresh();
                        ids.Add(p.Id); ws += p.WorkingSet64;
                        priv += p.PrivateMemorySize64; cpu += p.TotalProcessorTime.TotalSeconds;
                    }
                    catch { }
                }
                ids.Sort();
                string idsKey = string.Join(";", ids.ConvertAll(x => x.ToString()).ToArray());
                DateTime now = DateTime.Now;
                string cpuString = "";
                if (idsKey == lastGstIds && lastGstAt != DateTime.MinValue)
                {
                    double seconds = (now - lastGstAt).TotalSeconds;
                    if (seconds > 1)
                    {
                        double pct = Math.Max(0, Math.Min(100,
                            (cpu - lastGstCpu) / (seconds * Environment.ProcessorCount) * 100));
                        cpuString = pct.ToString("F1", CultureInfo.InvariantCulture);
                    }
                }
                lastGstCpu = cpu; lastGstAt = now; lastGstIds = idsKey;
                double w = ws / 1048576d, pr = priv / 1048576d;
                memory.Text = string.Format("WS {0:0}MB / Private {1:0}MB", w, pr);
                memory.ForeColor = w >= 1536 ? Color.Firebrick : Color.FromArgb(80, 88, 102);
                Directory.CreateDirectory(Logs);
                string csv = Path.Combine(Logs, "Memory_Trend.csv");
                if (!File.Exists(csv))
                    File.WriteAllText(csv, "Timestamp,PID,WorkingSet_MB,Private_MB,CPU_Percent\r\n", Encoding.UTF8);
                string row = now.ToString("yyyy-MM-dd HH:mm:ss") + "," + idsKey + "," +
                    w.ToString("F1", CultureInfo.InvariantCulture) + "," +
                    pr.ToString("F1", CultureInfo.InvariantCulture) + "," + cpuString + "\r\n";
                File.AppendAllText(csv, row, Encoding.UTF8);
            }
            catch (Exception ex) { Log("Health sample failed: " + ex.GetType().Name); }
            finally { foreach (Process p in procs) p.Dispose(); }
        }
        private void Cleanup()
        {
            timer.Stop(); timer.Dispose();
            StopNamer();
            if (worker != null) { worker.Dispose(); worker = null; }
            if (emergencyTask != null) { emergencyTask.Dispose(); emergencyTask = null; }
            tray.Visible = false; tray.Dispose();
        }
    }
}
