// Source identity comes from an ORIGINAL HeapAlloc call stack, not from
// HeapAlloc size, WPT Source=LFH, a later ReAlloc stack or a stack-group
// outstanding count. This probe runs ONLY on a disposable known native
// fixture in GitHub Windows CI; no real GIO or recorder approval.
using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Diagnostics.Symbols;
using Microsoft.Diagnostics.Tracing;
using Microsoft.Diagnostics.Tracing.Etlx;
using Microsoft.Diagnostics.Tracing.Parsers.Kernel;

internal static class Program
{
    private const string NativeModule = "c545d_realloc_cal";
    private const string NativeOriginalFunction = "mixed_alloc";
    private const int MaxFixtureEvents=100_000;

    private readonly record struct Frame(string? Module, string? Function);
    private readonly record struct StackVerdict(bool Present,bool FixtureModule,bool ExactOriginalMethod);

    private static StackVerdict Classify(IReadOnlyList<Frame>? frames)
    {
        if(frames is null || frames.Count==0)
            return new StackVerdict(false,false,false);
        bool native=false,matched=false;
        if(frames.Count>256)
            throw new ArgumentException("stack_depth_unbounded");
        foreach(var f in frames)
        {
            if(f.Module is null || f.Module.Length>256 ||
               (f.Function is not null && f.Function.Length>2048))
                continue;
            if(!string.Equals(f.Module,NativeModule,StringComparison.OrdinalIgnoreCase))
                continue;
            native=true;
            if(string.Equals(f.Function,NativeOriginalFunction,StringComparison.Ordinal) ||
               string.Equals(f.Function,NativeOriginalFunction+"()",StringComparison.Ordinal))
                matched=true;
        }
        return new StackVerdict(true,native,matched);
    }

    private static void SelfTest()
    {
        static void Expect(bool good) {if(!good)throw new InvalidOperationException("stack_source_contract_failed");}
        var positive=Classify(new Frame[]{
            new("ntdll","RtlAllocateHeap"),new(NativeModule,NativeOriginalFunction),
            new("kernelbase","HeapAlloc")
        });
        Expect(positive.Present&&positive.FixtureModule&&positive.ExactOriginalMethod);
        var negative=new IReadOnlyList<Frame>?[]{
            null,Array.Empty<Frame>(),
            new Frame[]{new("kernelbase","HeapAlloc")},
            new Frame[]{new("c545d_realloc_cal_wrong",NativeOriginalFunction)},
            new Frame[]{new(NativeModule,null)},
            new Frame[]{new(NativeModule,"mixed_realloc")},
            new Frame[]{new(NativeModule,"mixed_alloc_lookalike")},
            new Frame[]{new(NativeModule,"0xDEADBEEF")},
            new Frame[]{new("gio-2.0-0",NativeOriginalFunction)},
            new Frame[]{new("kernelbase",NativeOriginalFunction),new(NativeModule,null)},
            new Frame[]{new(NativeModule,"unverified_source_alloc")}
        };
        int tested=0;
        foreach(var frames in negative)
        {
            if(Classify(frames).ExactOriginalMethod)
                throw new InvalidOperationException("false_positive_original_stack_source");
            tested++;
        }
        // A stack exists, but the allocating source method has NOT been
        // symbolically proven. This cannot be promoted to real GIO owner.
        Expect(Classify(new Frame[]{new(NativeModule,null)}).FixtureModule);
        Console.WriteLine($"C545D_ETLX_ORIGINAL_STACK_SELFTEST_PASS,positive=1,negative={tested},"+
            "module_only_not_owner=1,realloc_stack_not_alloc_owner=1,"+
            "untrusted_symbol_not_owner=1,real_GIO_tested=0,release_HOLD=1");
    }

    private static int Probe(string[] args)
    {
        if(args.Length!=5 || args[0]!="--etl" || args[2]!="--pid" ||
           args[4]!="--preworkload-and-losszero-verified")
            throw new ArgumentException("invalid_etlx_stack_cli");
        if(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")!="true" ||
           Environment.GetEnvironmentVariable("RUNNER_OS")!="Windows")
            throw new ArgumentException("disposable_windows_ci_only");

        string? runner=Environment.GetEnvironmentVariable("RUNNER_TEMP");
        if(string.IsNullOrWhiteSpace(runner))
            throw new ArgumentException("private_runner_not_verified");
        string root=Path.GetFullPath(runner);
        string etl=Path.GetFullPath(args[1]);
        if(!etl.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("etl_outside_private_runner");
        var file=new FileInfo(etl);
        if(!file.Exists || file.Length<512 || file.Length>128*1024*1024)
            throw new ArgumentException("etl_absent_or_oversized");
        if(!int.TryParse(args[3],out int pid)||pid<=0)
            throw new ArgumentException("invalid_owned_pid");
        string fixtureRoot=Path.GetDirectoryName(etl)!;
        var pdb=new FileInfo(Path.Combine(fixtureRoot,"realloc.pdb"));
        if(!pdb.Exists||pdb.Length<512||pdb.Length>16*1024*1024)
            throw new ArgumentException("trusted_native_fixture_pdb_missing");
        string exe=Path.Combine(fixtureRoot,NativeModule+".exe");
        if(!File.Exists(exe))
            throw new ArgumentException("original_native_fixture_exe_missing");

        int alloc=0,hasStack=0,hasNative=0,exactMethod=0,nonfixture=0;
        int symbolsAttempted=0;
        using(var log=TraceLog.OpenOrConvert(etl,new TraceLogOptions{ConversionLog=TextWriter.Null}))
        {
            var proc=log.Processes.LastProcessWithID(pid);
            if(proc is null)
                throw new ArgumentException("etl_process_metadata_missing");
            using(var reader=new SymbolReader(TextWriter.Null,fixtureRoot))
            {
                reader.Options=SymbolReaderOptions.CacheOnly;
                // Never permit symsrv, source server, unexpected folder or
                // external-PDB lookup. This fixture PDB is produced locally.
                reader.SecurityCheck=path =>
                {
                    try
                    {
                        string full=Path.GetFullPath(path);
                        return full.StartsWith(fixtureRoot+Path.DirectorySeparatorChar,
                            StringComparison.OrdinalIgnoreCase);
                    }
                    catch{return false;}
                };
                foreach(var mod in proc.LoadedModules)
                {
                    if(!string.Equals(mod.Name,NativeModule,StringComparison.OrdinalIgnoreCase))
                        continue;
                    symbolsAttempted++;
                    log.CodeAddresses.LookupSymbolsForModule(reader,mod.ModuleFile);
                }
            }

            using(var source=log.Events.GetSource())
            {
                var heap=new HeapTraceProviderTraceEventParser(source);
                heap.HeapTraceAlloc+=data=>
                {
                    if(data.ProcessID!=pid)return;
                    if(++alloc>MaxFixtureEvents)
                        throw new ArgumentException("unbounded_selected_heap_events");
                    if(data.AllocSize!=192 && data.AllocSize!=448 && data.AllocSize!=832)
                    {
                        nonfixture++;
                        return;
                    }
                    var frames=new List<Frame>();
                    var stack=data.CallStack();
                    int depth=0;
                    while(stack is not null && depth<256)
                    {
                        var code=stack.CodeAddress;
                        frames.Add(new Frame(code.ModuleFile?.Name,
                            code.Method?.FullMethodName));
                        stack=stack.Caller;
                        depth++;
                    }
                    if(stack is not null)
                        throw new ArgumentException("stack_depth_unbounded");
                    var verdict=Classify(frames);
                    if(verdict.Present)hasStack++;
                    if(verdict.FixtureModule)hasNative++;
                    if(verdict.ExactOriginalMethod)exactMethod++;
                };
                source.Process();
            }
        }
        // Count fixture allocations separately: total selected-PID allocations
        // includes unrelated Windows runtime events of other sizes.
        if(alloc<24 || alloc>MaxFixtureEvents)
            throw new ArgumentException("heap_stack_source_trace_incomplete");
        int selected=alloc-nonfixture;
        Console.WriteLine($"C545D_ETLX_ORIGINAL_ALLOC_STACK_AUDIT,selected_alloc={selected},"+
            $"original_stack_attached={hasStack},fixture_module_seen={hasNative},"+
            $"exact_native_alloc_method={exactMethod},unresolved_original_alloc={selected-exactMethod},"+
            $"native_symbol_lookup_modules={symbolsAttempted},events_heap_alloc={alloc},"+
            "unresolved_source_class_never_guessed=1,"+
            "original_heap_source_not_LFH_inferred=1,real_GIO_owner_proven=0,"+
            "raw_etl_uploaded=0,pointers_logged=0,release_HOLD=1");
        if(selected!=24 || exactMethod!=24 || symbolsAttempted!=1)
            throw new ArgumentException("original_alloc_stack_source_incomplete");
        Console.WriteLine("C545D_ETLX_ORIGINAL_ALLOC_SOURCE_PASS,known_fixture=1,"+
            "all_24_native_original_alloc_functions_proven=1,"+
            "realloc_source_not_substituted=1,real_GIO_stack_proven=0,release_HOLD=1");
        return 0;
    }

    private static int Main(string[] args)
    {
        try
        {
            if(args.Length==1 && args[0]=="--selftest")
            {
                SelfTest();
                return 0;
            }
            return Probe(args);
        }
        catch(ArgumentException)
        {
            Console.WriteLine("C545D_ETLX_ORIGINAL_ALLOC_SOURCE_GAP,"+
                "reason=stack_source_or_contract_unverified,real_GIO_owner_proven=0,"+
                "raw_uploaded=0,release_HOLD=1");
            return 2;
        }
        catch(Exception)
        {
            Console.WriteLine("C545D_ETLX_ORIGINAL_ALLOC_SOURCE_GAP,"+
                "reason=ETLX_or_symbol_reader_unverified,real_GIO_owner_proven=0,"+
                "raw_uploaded=0,release_HOLD=1");
            return 3;
        }
    }
}
