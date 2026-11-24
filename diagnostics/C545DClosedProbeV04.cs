// v0.4 development candidate. Optional diagnostics; not approved for installation.
// No directory enumeration, no network, no raw paths in the result.
// The trusted local directory must not be concurrently manipulated by another actor.
using System;
using System.IO;
using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

public static class C545DClosedProbeV04 {
    public sealed class Result {
        public string Status = "unknown";
        public string Json = ""; // Internal only; pass to numeric allowlist classifier, never export.
        public int ExitCode = -1;
        public int Started = 0;
        public int ChildExited = 0;
    }
    sealed class Capture {
        public string Text = "";
        public bool Overflow;
    }
    static async Task<Capture> Drain(StreamReader reader, bool keep) {
        var buffer = new char[2048];
        var data = new StringBuilder();
        int total = 0;
        while (true) {
            int n = await reader.ReadAsync(buffer, 0, buffer.Length).ConfigureAwait(false);
            if (n == 0) return new Capture { Text = data.ToString() };
            total += n;
            if (total > 65536) return new Capture { Overflow = true };
            if (keep) data.Append(buffer, 0, n);
        }
    }
    // Generic entry solely for synthetic subprocess tests; only ProbeFinalized invokes ffprobe.
    private static Result RunBounded(string executable, string args, int timeoutMs) {
        var result = new Result();
        if (timeoutMs < 100 || timeoutMs > 10000) { result.Status = "invalid_timeout"; return result; }
        Process p = null;
        Task<Capture> stdout = null, stderr = null;
        try {
            var start = new ProcessStartInfo(executable, args) {
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true
            };
            var clock = Stopwatch.StartNew();
            p = Process.Start(start);
            if (p == null) { result.Status = "start_failed"; return result; }
            result.Started = 1;
            stdout = Drain(p.StandardOutput, true);
            stderr = Drain(p.StandardError, false);
            while (true) {
                if (stdout.IsFaulted || stderr.IsFaulted || stdout.IsCanceled || stderr.IsCanceled) {
                    result.Status = "read_failed"; break;
                }
                if ((stdout.IsCompleted && stdout.Result.Overflow) ||
                    (stderr.IsCompleted && stderr.Result.Overflow)) {
                    result.Status = "output_limit"; break;
                }
                if (p.HasExited && stdout.IsCompleted && stderr.IsCompleted) {
                    result.ExitCode = p.ExitCode;
                    result.Status = result.ExitCode == 0 ? "ok" : "probe_failed";
                    if (result.ExitCode == 0) result.Json = stdout.Result.Text;
                    break;
                }
                if (clock.ElapsedMilliseconds >= timeoutMs) { result.Status = "timeout"; break; }
                Thread.Sleep(10);
            }
        } catch { result.Status = "process_error"; }
        finally {
            if (p != null) {
                try {
                    if (!p.HasExited) p.Kill(); // Only the child started by this method.
                    if (p.WaitForExit(1000)) result.ChildExited = 1;
                    else { result.Status = "cleanup_unconfirmed"; result.Json = ""; }
                } catch { result.Status = "cleanup_unconfirmed"; result.Json = ""; }
                finally {
                    try { p.StandardOutput.Dispose(); } catch { }
                    try { p.StandardError.Dispose(); } catch { }
                    p.Dispose();
                }
            }
            // Observe already-faulted tasks without waiting indefinitely for pipe EOF.
            if (stdout != null && stdout.IsFaulted) { var ignored = stdout.Exception; }
            if (stderr != null && stderr.IsFaulted) { var ignored = stderr.Exception; }
        }
        return result;
    }
    public static bool IsSafeLocalDirectory(string directory) {
        if (!Regex.IsMatch(directory, @"^[A-Za-z]:\\") || directory.IndexOf('"') >= 0) return false;
        var d = new DirectoryInfo(directory);
        if (new DriveInfo(d.Root.FullName).DriveType != DriveType.Fixed) return false;
        while (d != null) {
            if (!d.Exists || (d.Attributes & FileAttributes.ReparsePoint) != 0) return false;
            d = d.Parent;
        }
        return true;
    }
    public static Result ProbeFinalized(string trustedRoot, string renamedLeaf, bool renameSucceeded,
                                        string trustedProbeExe, int timeoutMs) {
        var result = new Result();
        if (!renameSucceeded) { result.Status = "no_rename_evidence"; return result; }
        if (String.IsNullOrEmpty(renamedLeaf) ||
            !Regex.IsMatch(renamedLeaf, @"\A[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}(?:_[0-9]{2,9})?\.mp4\z")) {
            result.Status = "name_rejected"; return result;
        }
        return ProbeLocalLeaf(trustedRoot, renamedLeaf, trustedProbeExe, timeoutMs);
    }
    // CI-only candidate: existing renamer's exclusive-open check already succeeded.
    // Independently acquire a read lease before launching ffprobe; pending name alone is not evidence.
    public static Result ProbeRenameCandidate(string trustedRoot, string pendingLeaf, bool exclusiveGatePassed,
                                              string trustedProbeExe, int timeoutMs) {
        var result = new Result();
        if (!exclusiveGatePassed) { result.Status = "no_close_gate"; return result; }
        if (String.IsNullOrEmpty(pendingLeaf) ||
            !Regex.IsMatch(pendingLeaf, @"\A(?:[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{3}_[0-9]{5}|C545D_PENDING_[0-9]{8}_[0-9]{6}_[0-9a-fA-F]{8}_[0-9]{5})\.mp4\z")) {
            result.Status = "name_rejected"; return result;
        }
        return ProbeLocalLeaf(trustedRoot, pendingLeaf, trustedProbeExe, timeoutMs);
    }
    static Result ProbeLocalLeaf(string trustedRoot, string renamedLeaf, string trustedProbeExe, int timeoutMs) {
        var result = new Result();
        try {
            if (String.IsNullOrEmpty(trustedRoot) || !Regex.IsMatch(trustedRoot, @"^[A-Za-z]:\\")) {
                result.Status = "root_rejected"; return result;
            }
            string root = Path.GetFullPath(trustedRoot);
            if (!IsSafeLocalDirectory(root)) { result.Status = "root_rejected"; return result; }
            if (String.IsNullOrEmpty(trustedProbeExe) || !Path.IsPathRooted(trustedProbeExe) ||
                !String.Equals(Path.GetFileName(trustedProbeExe), "ffprobe.exe", StringComparison.OrdinalIgnoreCase) ||
                !File.Exists(trustedProbeExe)) { result.Status = "probe_unavailable"; return result; }
            string path = Path.Combine(root, renamedLeaf);
            if (!File.Exists(path)) { result.Status = "missing_file"; return result; }
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) {
                result.Status = "reparse_rejected"; return result;
            }
            FileStream lease;
            try { lease = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read); }
            catch (IOException) { result.Status = "file_busy_or_unavailable"; return result; }
            using (lease) {
                if (!IsSafeLocalDirectory(root) || (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) {
                    result.Status = "reparse_rejected"; return result;
                }
                // FileShare.Read holds a non-writer, non-delete lease for the probe.
                // Restrict demuxer/protocol and disable MOV external data references.
                string args = "-v error -protocol_whitelist file -f mov -enable_drefs 0 -use_absolute_path 0 " +
                    "-show_entries stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels:format=duration " +
                    "-of json -i \"" + path + "\"";
                return RunBounded(trustedProbeExe, args, timeoutMs);
            }
        } catch { result.Status = "file_unavailable"; return result; }
    }
}
