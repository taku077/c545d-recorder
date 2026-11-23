// Original GIO allocation method owner census from a tiny PRE-FIRST-AppInfo
// ETW interval on a DISPOSABLE Windows2022 worker. Never run on recorder host.
// A stack with gio DLL only is NOT a resolved original allocating function.
// CodeView RSDS/PDB GUID+age is verified independently before invocation.
// A source token is inherited through ReAlloc old/new and logical Free.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Microsoft.Diagnostics.Symbols;
using Microsoft.Diagnostics.Tracing;
using Microsoft.Diagnostics.Tracing.Etlx;
using Microsoft.Diagnostics.Tracing.Parsers.Kernel;

internal static class Program
{
    private const int EventCap=390000;
    private const string GioModule="gio-2.0-0";
    private readonly record struct Frame(string? Module,string? Function);
    private readonly record struct Owner(bool HasStack,bool HasGioFrame,bool ExactGioMethod);
    private static readonly HashSet<string> TrustedGioMethods=new(StringComparer.Ordinal)
    {
        "update_registry_data",
        "keys_updated",
        "watch_keys",
        "gio_win32_appinfo_thread_func",
        "g_win32_registry_key_watch",
        "g_win32_package_parser_enum_packages"
    };

    private static string? NormalizeFunction(string? symbol)
    {
        if(symbol is null || symbol.Length<1 || symbol.Length>2048)
            return null;
        // TraceEvent Method.FullMethodName may include C signature suffix.
        // Only accept exact name or exact name followed by '('.
        int paren=symbol.IndexOf('(');
        var method=paren>=0?symbol[..paren]:symbol;
        return method;
    }

    private static Owner Classify(IReadOnlyList<Frame>? frames)
    {
        if(frames is null || frames.Count==0)return new(false,false,false);
        if(frames.Count>256)throw new ArgumentException("stack_depth_exceeded");
        bool gio=false,method=false;
        foreach(var f in frames)
        {
            string? name=f.Module?.EndsWith(".dll",StringComparison.OrdinalIgnoreCase)==true
                ? f.Module[..^4] : f.Module;
            if(!string.Equals(name,GioModule,StringComparison.OrdinalIgnoreCase))
                continue;
            gio=true;
            var exact=NormalizeFunction(f.Function);
            if(exact is not null && TrustedGioMethods.Contains(exact))
                method=true;
        }
        return new(true,gio,method);
    }

    private static void SelfTest()
    {
        static void Expect(bool good){if(!good)throw new InvalidOperationException("source_owner_test_failed");}
        var positive=Classify(new Frame[]{new("ntdll","RtlAllocateHeap"),
            new("gio-2.0-0.dll","update_registry_data"),new("glib-2.0-0","g_malloc")});
        Expect(positive.HasGioFrame&&positive.ExactGioMethod);
        var bad=new IReadOnlyList<Frame>?[]{
            null,Array.Empty<Frame>(),
            new Frame[]{new("glib-2.0-0","update_registry_data")},
            new Frame[]{new("gio-2.0-0",null)},
            new Frame[]{new("gio-2.0-0","0xFFAA")},
            new Frame[]{new("gio-2.0-0","update_registry_data_wrong")},
            new Frame[]{new("gio-2.0-0","g_win32_registry_key_watchlookalike")},
            new Frame[]{new("gio-2.0-0-malicious","update_registry_data")},
            new Frame[]{new("gio-2.0-0","HeapAlloc")},
            new Frame[]{new("gio-2.0-0","mixed_alloc")},
            new Frame[]{new("gio-2.0-0","update_registry_data old_symbols")},
            new Frame[]{new("unknown","update_registry_data")}
        };
        for(int i=0;i<bad.Length;i++)
            Expect(!Classify(bad[i]).ExactGioMethod);
        Expect(Classify(new Frame[]{new("gio-2.0-0",null)}).HasGioFrame);
        var lifetime=new GenericHeapLifetime();
        lifetime.Alloc(12,100,168,GenericHeapLifetime.OriginProof.VerifiedGioMethod);
        lifetime.Free(12,100);
        lifetime.Realloc(12,100,200,168,240);
        lifetime.Free(12,200);
        lifetime.FinalizePending();
        Expect(lifetime.GioMethodOriginalAllocations==1 &&
               lifetime.GioMethodLinkedReallocations==1 &&
               lifetime.GioMethodLogicalFrees==1 &&
               lifetime.ProvenOriginalAllocations==0 &&
               lifetime.Snapshot().Count==0);
        Console.WriteLine("C545D_GIO_ETLX_SOURCE_CLASSIFIER_SELFTEST_PASS,"+
            "positive=2,negative=12,module_only_rejected=1,"+
            "LFH_not_owner=1,original_stack_survives_realloc_free=1,"+
            "real_GIO_stacks_not_yet_examined=1,release_HOLD=1");
    }

    private static int Capture(string[] a)
    {
        if(a.Length!=9||a[0]!="--etl"||a[2]!="--pid"||
           a[4]!="--build"||a[6]!="--arm"||
           a[8]!="--preinit-losszero-and-pdb-match-verified")
            throw new ArgumentException("invalid_census_parameters");
        if(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")!="true" ||
           Environment.GetEnvironmentVariable("RUNNER_OS")!="Windows")
            throw new ArgumentException("not_isolated_windows_runner");
        var root=Environment.GetEnvironmentVariable("RUNNER_TEMP");
        if(string.IsNullOrWhiteSpace(root))
            throw new ArgumentException("private_runner_not_verified");
        string dir=Path.GetFullPath(root);
        string etl=Path.GetFullPath(a[1]);
        string build=Path.GetFullPath(a[5]);
        if(!etl.StartsWith(dir+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||
           !build.StartsWith(dir+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("untrusted_etl_or_build_dir");
        var fi=new FileInfo(etl);
        if(!fi.Exists||fi.Length<512||fi.Length>256*1024*1024)
            throw new ArgumentException("etlx_trace_missing_or_unbounded");
        if(!int.TryParse(a[3],out int pid) || pid<=0)
            throw new ArgumentException("invalid_owned_pid");
        string arm=a[7];
        if(arm!="registry" && arm!="nochange")
            throw new ArgumentException("unknown_disposable_arm");
        var model=new GenericHeapLifetime();
        int heapAlloc=0,heapEvents=0,heapRealloc=0,heapFree=0;
        int missingStack=0,hasGioModule=0,exactMethod=0,unknownOrigin=0;
        int orphanRealloc=0,orphanFree=0;
        int moduleCandidates=0,exactModulePdbLookups=0;
        using(var log=TraceLog.OpenOrConvert(etl,new TraceLogOptions{ConversionLog=TextWriter.Null}))
        {
            var process=log.Processes.LastProcessWithID(pid);
            if(process is null)throw new ArgumentException("selected_process_metadata_absent");
            using(var reader=new SymbolReader(TextWriter.Null,build))
            {
                reader.Options=SymbolReaderOptions.CacheOnly;
                reader.SecurityCheck=(path)=>
                {
                    try{return Path.GetFullPath(path).StartsWith(
                        build+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase);}
                    catch{return false;}
                };
                foreach(var m in process.LoadedModules)
                {
                    if(!string.Equals(m.Name,GioModule,StringComparison.OrdinalIgnoreCase))
                        continue;
                    moduleCandidates++;
                    log.CodeAddresses.LookupSymbolsForModule(reader,m.ModuleFile);
                    exactModulePdbLookups++;
                }
            }
            using(var src=log.Events.GetSource())
            {
                var heap=new HeapTraceProviderTraceEventParser(src);
                void Tick()
                {
                    if(++heapEvents>EventCap)
                        throw new ArgumentException("heap_event_capture_limit");
                }
                heap.HeapTraceAlloc+=ev=>
                {
                    if(ev.ProcessID!=pid)return;
                    Tick();heapAlloc++;
                    if(ev.AllocSize<=0)throw new ArgumentException("allocation_zero_size_unmodeled");
                    var frames=new List<Frame>();
                    var stack=ev.CallStack();
                    int depth=0;
                    while(stack is not null && depth<256)
                    {
                        var code=stack.CodeAddress;
                        frames.Add(new Frame(code.ModuleFile?.Name,
                            code.Method?.FullMethodName));
                        stack=stack.Caller;depth++;
                    }
                    if(stack is not null)
                        throw new ArgumentException("stack_depth_limit");
                    var result=Classify(frames);
                    if(!result.HasStack)missingStack++;
                    if(result.HasGioFrame)hasGioModule++;
                    if(result.ExactGioMethod)exactMethod++; else unknownOrigin++;
                    model.Alloc(ev.HeapHandle,ev.AllocAddress,ev.AllocSize,
                        result.ExactGioMethod
                        ? GenericHeapLifetime.OriginProof.VerifiedGioMethod
                        : GenericHeapLifetime.OriginProof.Unresolved);
                };
                heap.HeapTraceReAlloc+=ev=>
                {
                    if(ev.ProcessID!=pid)return;
                    Tick();heapRealloc++;
                    if(model.IsTracked(ev.HeapHandle,ev.OldAllocAddress))
                        model.Realloc(ev.HeapHandle,ev.OldAllocAddress,
                            ev.NewAllocAddress,ev.OldAllocSize,ev.NewAllocSize);
                    else orphanRealloc++;
                };
                heap.HeapTraceFree+=ev=>
                {
                    if(ev.ProcessID!=pid)return;
                    Tick();heapFree++;
                    if(model.IsTracked(ev.HeapHandle,ev.FreeAddress))
                        model.Free(ev.HeapHandle,ev.FreeAddress);
                    else orphanFree++;
                };
                src.Process();
            }
        }
        model.FinalizePending();
        var snapshot=model.Snapshot();
        Console.WriteLine($"C545D_GIO_ETLX_FIRST_SOURCE_CENSUS,arm={arm},"+
            $"pid_heap_events={heapEvents},original_alloc_events={heapAlloc},"+
            $"realloc_events={heapRealloc},free_events={heapFree},"+
            $"missing_initial_stack={missingStack},gio_module_in_alloc_stack={hasGioModule},"+
            $"exact_GIO_source_method_on_original_alloc={exactMethod},"+
            $"unknown_origin_original_alloc={unknownOrigin},"+
            $"gio_source_origin_realloc={model.GioMethodLinkedReallocations},"+
            $"gio_source_origin_logical_free={model.GioMethodLogicalFrees},"+
            $"gio_source_origin_alloc={model.GioMethodOriginalAllocations},"+
            $"original_allocation_live={snapshot.Count},"+
            $"request_bytes_live={snapshot.Bytes},"+
            $"unknown_original_live={snapshot.Unresolved},"+
            $"orphan_realloc_prior_start={orphanRealloc},"+
            $"orphan_free_prior_start={orphanFree},"+
            $"native_GIO_loaded_modules={moduleCandidates},"+
            $"native_GIO_symbol_lookups={exactModulePdbLookups},"+
            "before_first_appinfo=1,after_settled_cleanup=1,"+
            "source_closed_globally=0,leak_proven=0,release_HOLD=1,"+
            "no_raw_pointer_or_stack_output=1");
        if(moduleCandidates!=1||exactModulePdbLookups!=1||
           heapAlloc<1||hasGioModule<1||exactMethod<1)
            throw new ArgumentException("actual_GIO_source_function_not_proven");
        Console.WriteLine($"C545D_GIO_ETLX_FIRST_SOURCE_OWNER_PASS,arm={arm},"+
            "real_GIO_method_stacks_found=1,source_owner_lifetime_annotated=1,"+
            "no_global_quiet_or_leak_claim=1,release_HOLD=1,raw_uploaded=0");
        return 0;
    }

    private static int Main(string[] args)
    {
        try
        {
            if(args.Length==1 && args[0]=="--selftest"){SelfTest();return 0;}
            return Capture(args);
        }
        catch(ArgumentException)
        {
            Console.WriteLine("C545D_GIO_ETLX_FIRST_SOURCE_GAP,"+
                "reason=source_history_or_symbol_scope_unverified,"+
                "raw_uploaded=0,release_HOLD=1");
            return 2;
        }
        catch(Exception)
        {
            Console.WriteLine("C545D_GIO_ETLX_FIRST_SOURCE_GAP,"+
                "reason=ETLX_decode_or_symbol_resolution_unverified,"+
                "raw_uploaded=0,release_HOLD=1");
            return 3;
        }
    }
}
