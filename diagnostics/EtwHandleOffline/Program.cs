using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Windows.EventTracing;
using Microsoft.Windows.EventTracing.Memory;
using Microsoft.Windows.EventTracing.Symbols;

internal static class Program
{
    private sealed class Group
    {
        public int Created { get; set; }
        public int NoCloseObserved { get; set; }
        public int WithCreateStack { get; set; }
        public HashSet<string> Functions { get; } = new(StringComparer.Ordinal);
    }

    private static readonly HashSet<string> PublicModuleNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "ntdll", "kernelbase", "kernel32", "advapi32", "sechost", "bcrypt", "rpcrt4",
        "combase", "ole32", "oleaut32", "ucrtbase", "msvcrt", "win32u", "user32",
        "gstreamer-1.0-0", "gstbase-1.0-0", "gstvideo-1.0-0", "gstisomp4",
        "gstvideoparsersbad", "gstlibav", "glib-2.0-0", "gobject-2.0-0",
        "gio-2.0-0", "gstcoreelements", "gstrtpmanager",
        "avcodec-61", "avutil-59", "avformat-61", "x264"
    };

    private static string SafeModule(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return "unknown-module";
        string stem = Path.GetFileName(raw.Replace('/', '\\')).ToLowerInvariant();
        if (stem.EndsWith(".dll", StringComparison.Ordinal)) stem = stem[..^4];
        if (stem.EndsWith(".exe", StringComparison.Ordinal)) stem = stem[..^4];
        if (PublicModuleNames.Contains(stem)) return stem;
        if (Regex.IsMatch(stem, @"^(lib)?(gst|gstreamer|glib|gobject|gio|avcodec|avutil|avformat|swscale|swresample)[a-z0-9_.-]{0,30}$"))
            return Regex.IsMatch(stem, @"^(lib)?(gst[a-z0-9_.-]+|av[a-z0-9_.-]+)$") ? "media-other" : "media-other";
        return "other-module";
    }

    private static string SafeFunction(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return "";
        // Never emit C++ template arguments, paths, usernames, or unknown content.
        if (!Regex.IsMatch(raw, @"^[A-Za-z_][A-Za-z0-9_:.]{0,90}$")) return "";
        return raw;
    }

    private static string[] VisibleStack(IStackSnapshot? stack, HashSet<string> publicFunctions)
    {
        if (stack == null) return Array.Empty<string>();
        var chain = new List<string>();
        foreach (var frame in stack.Frames)
        {
            string mod = SafeModule(frame.Image?.FileName);
            if (mod == "unknown-module" && frame.Symbol?.Image != null)
                mod = SafeModule(frame.Symbol.Image.FileName);
            if (mod != "unknown-module" && chain.Count < 30)
            {
                if (chain.Count == 0 || chain[^1] != mod) chain.Add(mod);
            }
            if (mod != "other-module" && mod != "unknown-module" && mod != "media-other")
            {
                string fun = SafeFunction(frame.Symbol?.FunctionName);
                if (!string.IsNullOrEmpty(fun) && publicFunctions.Count < 40)
                    publicFunctions.Add(mod + "!" + fun);
            }
        }
        return chain.ToArray();
    }

    private static int Main(string[] args)
    {
        try
        {
            if (args.Contains("--selftest", StringComparer.OrdinalIgnoreCase))
            {
                if (SafeModule(@"C:\Users\PRIVATE\secrets.dll") != "other-module" ||
                    SafeModule(@"C:\Program Files\GStreamer\gstisomp4.dll") != "gstisomp4" ||
                    SafeFunction(@"C:\Users\PRIVATE") != "" ||
                    SafeFunction("RegOpenKeyExW") != "RegOpenKeyExW")
                    throw new InvalidOperationException("Privacy selftest failure.");
                Console.WriteLine("SELFTEST_PASS: strict public-module/function sanitization.");
                return 0;
            }

            string? etl = null;
            int pid = 6168;
            string? outPath = null;
            bool useSymbols = false;
            for (int i = 0; i < args.Length; ++i)
            {
                switch (args[i])
                {
                    case "--etl": etl = args[++i]; break;
                    case "--pid": pid = int.Parse(args[++i]); break;
                    case "--out": outPath = args[++i]; break;
                    case "--symbols": useSymbols = true; break;
                    default: throw new ArgumentException("Usage: EtwHandleOffline.exe --etl FILE --pid 6168 --out FILE [--symbols]");
                }
            }
            if (etl == null || outPath == null || pid <= 0) throw new ArgumentException("ETL, output and PID required.");
            var input = new FileInfo(etl);
            if (!input.Exists || input.Length < 1024) throw new IOException("ETL missing or too small.");
            if (Path.GetFullPath(etl).Equals(Path.GetFullPath(outPath), StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Refusing to overwrite the original ETL.");
            Console.WriteLine("Offline ETL analysis: existing file only. No WPR/UST/recording operations.");
            Console.WriteLine("Using Microsoft TraceProcessing; handle type names may be unavailable in this API.");
            Console.WriteLine("Analyzing PID " + pid + " ...");

            long target = 0, withCreateTime = 0, noClose = 0, missingStack = 0, withStack = 0;
            long otherProcessCreated = 0;
            var groups = new Dictionary<string, Group>(StringComparer.Ordinal);
            using (ITraceProcessor trace = TraceProcessor.Create(input.FullName))
            {
                var pending = trace.UseHandles();
                IPendingResult<ISymbolDataSource>? pendingSymbols = null;
                if (useSymbols) pendingSymbols = trace.UseSymbols();
                trace.Process();
                if (useSymbols && pendingSymbols != null)
                {
                    // Opt-in only. May access symbol servers and use substantial CPU/disk resources.
                    Console.WriteLine("Optional symbol resolution requested.");
                    pendingSymbols.Result.LoadSymbolsForConsoleAsync(
                        SymCachePath.Automatic, SymbolPath.Automatic).GetAwaiter().GetResult();
                }
                foreach (var handle in pending.Result.OtherHandles)
                {
                    if (handle.Owner?.Id != pid) continue;
                    target++;
                    if (handle.CreatingProcess?.Id != pid) otherProcessCreated++;
                    if (!handle.CreateTime.HasValue) continue;
                    withCreateTime++;
                    bool unclosed = !handle.CloseTime.HasValue;
                    if (unclosed) noClose++;
                    if (handle.CreatingStack == null) missingStack++;
                    else withStack++;
                    var symbols = new HashSet<string>(StringComparer.Ordinal);
                    var modules = VisibleStack(handle.CreatingStack, symbols);
                    string key = modules.Length == 0 ? "(no recognized modules)" : string.Join(" -> ", modules);
                    if (!groups.TryGetValue(key, out var g)) groups[key] = g = new Group();
                    g.Created++;
                    if (unclosed) g.NoCloseObserved++;
                    if (modules.Length > 0) g.WithCreateStack++;
                    foreach (string f in symbols) if (g.Functions.Count < 20) g.Functions.Add(f);
                }
            }

            var output = new List<string>
            {
                "C545D ETL HANDLE STACK SAFE SUMMARY V1",
                "source_etl_included=no",
                "registry_paths_included=no",
                "raw_stack_addresses_included=no",
                "target_pid=" + pid,
                "trace_input_mb=" + Math.Round(input.Length / 1048576.0, 2),
                "generic_other_handles_owned_by_pid=" + target,
                "with_create_time=" + withCreateTime,
                "no_close_recorded=" + noClose,
                "with_create_stack=" + withStack,
                "missing_create_stack=" + missingStack,
                "creator_not_pid_or_missing=" + otherProcessCreated,
                "NOTE: API returns generic OtherHandles, not specific Key type. Never treat all rows as confirmed Key.",
                "NOTE: No close event recorded is not proof of an unclosed handle or a handle leak.",
                "NOTE: existing ETL may omit stacks or symbol names. No capture or recording changes.",
                "TOP_MODULE_CHAINS: occurrence counts and allowlisted modules only"
            };
            int rank = 0;
            foreach (var item in groups.OrderByDescending(x => x.Value.NoCloseObserved)
                                       .ThenByDescending(x => x.Value.Created).Take(15))
            {
                rank++;
                output.Add($"rank={rank} created={item.Value.Created} no_close_observed={item.Value.NoCloseObserved} modules={item.Key}");
                foreach (var symbol in item.Value.Functions.OrderBy(x => x).Take(6))
                    output.Add("  symbol=" + symbol);
            }
            if (target == 0) output.Add("STATUS=NO_GENERIC_HANDLES_FOUND_FOR_PID");
            else if (withStack == 0) output.Add("STATUS=NO_CREATE_STACKS_AVAILABLE");
            else output.Add("STATUS=STACK_MODULES_EXTRACTED_CHECK_ATTRIBUTION");

            var outputFull = Path.GetFullPath(outPath);
            Directory.CreateDirectory(Path.GetDirectoryName(outputFull)!);
            File.WriteAllLines(outputFull, output, new UTF8Encoding(false));
            Console.WriteLine("Safe summary saved: " + outputFull);
            Console.WriteLine("Raw ETL and source files were not modified.");
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("ANALYSIS_FAILED (" + ex.GetType().Name + "). Original ETL remains unchanged.");
            Console.Error.WriteLine("ReasonCode: " + ex.GetType().Name);
            return 1;
        }
    }
}
