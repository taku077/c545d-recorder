// Original GIO allocation method owner census from a tiny PRE-FIRST-AppInfo
// ETW interval on a DISPOSABLE Windows2022 worker. Never run on recorder host.
// A stack with gio DLL only is NOT a resolved original allocating function.
// CodeView RSDS/PDB GUID+age is verified independently before invocation.
// A source token is inherited through ReAlloc old/new and logical Free.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Globalization;
using Microsoft.Diagnostics.Symbols;
using Microsoft.Diagnostics.Tracing;
using Microsoft.Diagnostics.Tracing.Etlx;
using Microsoft.Diagnostics.Tracing.Parsers.Kernel;

// TraceEvent exposes its raw ETW QPC as a discouraged but documented API.
// Phase matching MUST use raw counter ticks from the same Windows session;
// RelativeMSec would introduce an independent clock-origin conversion.
#pragma warning disable CS0618

internal static class Program
{
    // The one-cycle real GIO registry arm already reached 390000 typed events
    // (196874 alloc +1476 realloc +191650 free), while the nochange arm
    // completed at 168450. This is an event-count ceiling, not a source
    // owner or allocation leak. Bound the private ETL file at 256 MiB and
    // replay at most two million typed events to cover the new discriminator.
    private const int EventCap=2_000_000;
    private static string diagnosticStage="not_started";
    private static int countZeroAlloc,countZeroRealloc,countZeroOldSize,
        countZeroNewSize, countAlloc,countRealloc,countFree,missingStacks,
        hasGioFrameCount,exactMethodCount,loadedGioModules,lookupModules;
    private static GenericHeapLifetime? currentLifetime;
    private static readonly HashSet<string> SafeArgumentReasons=new(StringComparer.Ordinal)
    {
        "invalid_census_parameters","not_isolated_windows_runner",
        "private_runner_not_verified","untrusted_etl_or_build_dir",
        "etlx_trace_missing_or_unbounded","invalid_owned_pid",
        "unknown_disposable_arm","selected_process_metadata_absent",
        "stack_depth_limit","heap_event_capture_limit",
        "stack_depth_exceeded",
        "invalid_heap_event_identity_or_size","overlapping_live_allocation",
        "orphan_realloc_prior_alloc_not_observed",
        "stale_provisional_free_cannot_match_realloc",
        "realloc_old_size_does_not_match","realloc_new_address_collision",
        "invalid_free_identity","duplicate_provisional_free",
        "orphan_free_or_stale_realloc_address",
        "cohort_invalid_original","cohort_overlapping_live",
        "cohort_invalid_realloc","cohort_unproven_old_realloc",
        "cohort_old_size_mismatch","cohort_new_target_pending",
        "cohort_unproven_new_target","cohort_free_not_owned",
        "cohort_pending_not_finalized","cohort_lifetime_not_balanced",
        "cohort_generic_reconciliation_failed",
        "cohort_realloc_crosses_epoch_cut",
        "active_epoch_qpc_parameters_invalid",
        "active_epoch_event_qpc_order_unverified",
        "active_epoch_first_cut_not_inside_trace",
        "active_epoch_snapshot_totals_mismatch",
        "actual_GIO_source_function_not_proven"
    };
    private static string Diagnostic()
    {
        var p=currentLifetime?.Snapshot();
        return $",stage={diagnosticStage},"+
            $"alloc_observed={countAlloc},realloc_observed={countRealloc},"+
            $"zero_req_alloc={countZeroAlloc},zero_req_realloc={countZeroRealloc},"+
            $"zero_old_size_realloc={countZeroOldSize},zero_new_size_realloc={countZeroNewSize},"+
            $"free_observed={countFree},stack_missing={missingStacks},"+
            $"gio_module_in_original_stack={hasGioFrameCount},"+
            $"exact_gio_method={exactMethodCount},"+
            $"gio_modules_loaded={loadedGioModules},gio_module_symbol_lookup={lookupModules},"+
            $"tracked_live_count={p?.Count ?? 0},"+
            $"gio_origin_alloc={currentLifetime?.GioMethodOriginalAllocations ?? 0},"+
            $"gio_origin_realloc={currentLifetime?.GioMethodLinkedReallocations ?? 0},"+
            $"gio_origin_freed={currentLifetime?.GioMethodLogicalFrees ?? 0}";
    }
    private const string GioModule="gio-2.0-0";
    private readonly record struct Frame(string? Module,string? Function);
    private enum Cohort
    {
        MissingStack=0, NoGioFrame=1, GioMethodUnmatched=2,
        UpdateRegistryData=3, KeysUpdated=4, WatchKeys=5,
        AppinfoWorker=6, RegistryKeyWatch=7, PackageEnum=8,
        AmbiguousMultipleMethods=9
    }
    private readonly record struct Owner(bool HasStack,bool HasGioFrame,
        bool ExactGioMethod,Cohort Cohort,Cohort NearestKnown,bool FirstGioExact);
    private static readonly Dictionary<string,Cohort> TrustedGioMethods=
        new(StringComparer.Ordinal)
    {
        ["update_registry_data"]=Cohort.UpdateRegistryData,
        ["keys_updated"]=Cohort.KeysUpdated,
        ["watch_keys"]=Cohort.WatchKeys,
        ["gio_win32_appinfo_thread_func"]=Cohort.AppinfoWorker,
        ["g_win32_registry_key_watch"]=Cohort.RegistryKeyWatch,
        ["g_win32_package_parser_enum_packages"]=Cohort.PackageEnum
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
        if(frames is null || frames.Count==0)
            return new(false,false,false,Cohort.MissingStack,Cohort.MissingStack,false);
        if(frames.Count>256)throw new ArgumentException("stack_depth_exceeded");
        bool gio=false,firstGioExact=false;
        Cohort nearest=Cohort.GioMethodUnmatched;
        var hits=new HashSet<Cohort>();
        foreach(var f in frames)
        {
            string? name=f.Module?.EndsWith(".dll",StringComparison.OrdinalIgnoreCase)==true
                ? f.Module[..^4] : f.Module;
            if(!string.Equals(name,GioModule,StringComparison.OrdinalIgnoreCase))
                continue;
            bool firstGioFrame=!gio;
            gio=true;
            var exact=NormalizeFunction(f.Function);
            if(exact is not null && TrustedGioMethods.TryGetValue(exact,out var method))
            {
                hits.Add(method);
                // TraceEvent starts at event frame, then walks Caller.
                // Nearest allowlisted function is a PROXY, not proven direct origin.
                if(nearest==Cohort.GioMethodUnmatched)
                {
                    nearest=method;
                    firstGioExact=firstGioFrame;
                }
            }
        }
        // A stack containing multiple distinct allowlisted functions proves
        // GIO participation, NOT one arbitrary original allocating method.
        Cohort cohort=hits.Count>1?Cohort.AmbiguousMultipleMethods:
            hits.Count==1?hits.First():
            gio?Cohort.GioMethodUnmatched:Cohort.NoGioFrame;
        if(!gio)nearest=Cohort.NoGioFrame;
        return new(true,gio,hits.Count>0,cohort,nearest,firstGioExact);
    }

    // Separately audited method-level ledger; the existing size/address
    // generic lifetime model remains the independent total-count oracle.
    // All 10 cohorts are mutually exclusive, including explicit gap reasons.
    private sealed class MethodLedger
    {
        private const int Count=10;
        private const int MaxReallocGap=32;
        private readonly record struct Key(ulong Heap,ulong Address);
        private readonly record struct Entry(long Bytes,Cohort Cohort,long Birth,int Reallocs);
        private readonly record struct Held(Entry Entry,long Event,int Generation);
        private readonly Dictionary<Key,Entry> live=new();
        private readonly Dictionary<Key,Held> pending=new();
        private readonly long[] original=new long[Count];
        private readonly long[] reallocated=new long[Count];
        private readonly long[] freed=new long[Count];
        private long sequence;
        private int generation;
        internal void MarkEpochCut(){generation++;}

        internal void Alloc(ulong heap,ulong address,long size,Cohort source)
        {
            sequence++;
            if(heap==0||address==0||size<0||size>(1L<<36)||
               (int)source<0||(int)source>=Count)
                throw new ArgumentException("cohort_invalid_original");
            var key=new Key(heap,address);
            if(live.ContainsKey(key))
                throw new ArgumentException("cohort_overlapping_live");
            if(pending.Remove(key,out var old))
                freed[(int)old.Entry.Cohort]++;
            live.Add(key,new Entry(size,source,sequence,0));
            original[(int)source]++;
        }
        internal void Realloc(ulong heap,ulong oldAddress,ulong newAddress,
            long oldSize,long newSize)
        {
            sequence++;
            var before=new Key(heap,oldAddress);
            var after=new Key(heap,newAddress);
            if(heap==0||oldAddress==0||newAddress==0||
               oldSize<0||newSize<0||oldSize>(1L<<36)||newSize>(1L<<36))
                throw new ArgumentException("cohort_invalid_realloc");
            bool wasLive=live.TryGetValue(before,out var parent);
            if(!wasLive)
            {
                if(!pending.TryGetValue(before,out var saved)||
                   sequence-saved.Event<1||sequence-saved.Event>MaxReallocGap)
                    throw new ArgumentException("cohort_unproven_old_realloc");
                if(saved.Generation!=generation)
                    throw new ArgumentException("cohort_realloc_crosses_epoch_cut");
                parent=saved.Entry;
            }
            if(parent.Bytes!=oldSize)
                throw new ArgumentException("cohort_old_size_mismatch");
            if(after!=before)
            {
                if(pending.ContainsKey(after))
                    throw new ArgumentException("cohort_new_target_pending");
                if(live.TryGetValue(after,out var target))
                {
                    long gap=sequence-target.Birth;
                    if(target.Bytes!=newSize||target.Reallocs!=0||
                       gap<1||gap>MaxReallocGap)
                        throw new ArgumentException("cohort_unproven_new_target");
                    live.Remove(after);
                    original[(int)target.Cohort]--;
                }
            }
            if(wasLive)live.Remove(before);
            else pending.Remove(before);
            live.Add(after,new Entry(newSize,parent.Cohort,parent.Birth,
                parent.Reallocs+1));
            reallocated[(int)parent.Cohort]++;
        }
        internal void Free(ulong heap,ulong address)
        {
            sequence++;
            var key=new Key(heap,address);
            if(!live.Remove(key,out var value)||pending.ContainsKey(key))
                throw new ArgumentException("cohort_free_not_owned");
            pending.Add(key,new Held(value,sequence,generation));
        }
        internal void FinalizePending()
        {
            foreach(var held in pending.Values)
                freed[(int)held.Entry.Cohort]++;
            pending.Clear();
        }
        internal (long Original,long Reallocated,long Freed,long Live,long Bytes)
            Counts(Cohort cohort)
        {
            var index=(int)cohort;
            long count=0,bytes=0;
            foreach(var entry in live.Values)
                if(entry.Cohort==cohort){count++;bytes=checked(bytes+entry.Bytes);}
            return (original[index],reallocated[index],freed[index],count,bytes);
        }
        internal void CheckAgainst(GenericHeapLifetime generic)
        {
            if(pending.Count!=0)
                throw new ArgumentException("cohort_pending_not_finalized");
            var all=generic.Snapshot();
            long totalLive=0,totalBytes=0,knownOriginal=0,knownRealloc=0,
                knownFree=0;
            foreach(Cohort cohort in Enum.GetValues<Cohort>())
            {
                var x=Counts(cohort);
                if(x.Original<0||x.Freed<0||x.Original-x.Freed!=x.Live)
                    throw new ArgumentException("cohort_lifetime_not_balanced");
                totalLive+=x.Live;totalBytes=checked(totalBytes+x.Bytes);
                if(cohort>=Cohort.UpdateRegistryData)
                {
                    knownOriginal+=x.Original;
                    knownRealloc+=x.Reallocated;
                    knownFree+=x.Freed;
                }
            }
            if(totalLive!=all.Count||totalBytes!=all.Bytes||
               knownOriginal!=generic.GioMethodOriginalAllocations||
               knownRealloc!=generic.GioMethodLinkedReallocations||
               knownFree!=generic.GioMethodLogicalFrees)
                throw new ArgumentException("cohort_generic_reconciliation_failed");
        }
        internal void Report(string arm,bool nearest=false)
        {
            foreach(Cohort cohort in Enum.GetValues<Cohort>())
            {
                var x=Counts(cohort);
                string label=nearest?"C545D_GIO_NEAREST_METHOD_COHORT,":
                    "C545D_GIO_METHOD_COHORT,";
                string proof=nearest
                    ? "nearest_allowlisted_proxy=1,exact_alloc_owner_not_proven=1,release_HOLD=1"
                    : "source_original_stack_only=1,global_leak_proven=0,release_HOLD=1";
                Console.WriteLine(label+
                    $"arm={arm},category={cohort},"+
                    $"original={x.Original},realloc={x.Reallocated},"+
                    $"logical_free={x.Freed},live={x.Live},"+
                    $"request_bytes_live={x.Bytes},"+proof);
            }
        }
    }

    // Snapshot the SAME continuous original-allocation ledgers at each
    // process-local QPC cut. The strict multi-GIO ambiguity remains intact;
    // the nearest-allowlisted ledger is ONLY a deterministic stack proxy.
    // A Free-before-ReAlloc spanning a cut is rejected, not silently
    // converted into proof of a live/leaked original allocation.
    private sealed class ActiveEpochCuts
    {
        private static readonly string[] Names={"baseline","cycle1","cycle2"};
        private readonly long[] cutoffs;
        private readonly List<(long Count,long Bytes,(long Live,long Bytes)[] Strict,
            (long Live,long Bytes)[] Nearest)> samples=new();
        private int next;
        private long lastQpc;
        private bool sawEventBeforeBaseline,sawEventAfterBaseline;
        internal ActiveEpochCuts(long b,long c1,long c2)
        {
            if(b<=0||b>=c1||c1>=c2)
                throw new ArgumentException("active_epoch_qpc_parameters_invalid");
            cutoffs=new[]{b,c1,c2};
        }
        internal void OnHeapEvent(long qpc,GenericHeapLifetime generic,
            MethodLedger strict,MethodLedger nearest)
        {
            if(qpc<=0||qpc<lastQpc)
                throw new ArgumentException("active_epoch_event_qpc_order_unverified");
            if(qpc<cutoffs[0])sawEventBeforeBaseline=true;
            if(qpc>cutoffs[0])sawEventAfterBaseline=true;
            lastQpc=qpc;
            while(next<cutoffs.Length && qpc>=cutoffs[next])
                Cut(generic,strict,nearest);
        }
        private void Cut(GenericHeapLifetime generic,MethodLedger strict,
            MethodLedger nearest)
        {
            var all=generic.Snapshot();
            var a=new (long Live,long Bytes)[10];
            var b=new (long Live,long Bytes)[10];
            long al=0,ab=0,bl=0,bb=0;
            foreach(Cohort cohort in Enum.GetValues<Cohort>())
            {
                var x=strict.Counts(cohort);
                var y=nearest.Counts(cohort);
                a[(int)cohort]=(x.Live,x.Bytes);
                b[(int)cohort]=(y.Live,y.Bytes);
                al+=x.Live;ab=checked(ab+x.Bytes);
                bl+=y.Live;bb=checked(bb+y.Bytes);
            }
            if(al!=all.Count||bl!=all.Count||
               ab!=all.Bytes||bb!=all.Bytes)
                throw new ArgumentException("active_epoch_snapshot_totals_mismatch");
            samples.Add((all.Count,all.Bytes,a,b));
            strict.MarkEpochCut();
            nearest.MarkEpochCut();
            next++;
        }
        internal void Finish(GenericHeapLifetime generic,MethodLedger strict,
            MethodLedger nearest)
        {
            if(!sawEventBeforeBaseline||!sawEventAfterBaseline)
                throw new ArgumentException("active_epoch_first_cut_not_inside_trace");
            // The controller must independently attest the ETW logger remained
            // armed until after cycle2's marker (postsettle fence). If no heap
            // events occurred after a cut, the state at the end is unchanged.
            while(next<cutoffs.Length)Cut(generic,strict,nearest);
            if(samples.Count!=3)
                throw new ArgumentException("active_epoch_snapshot_totals_mismatch");
        }
        internal (long Live,long Bytes) Read(int phase,Cohort cohort,bool nearest)
        {
            if(phase<0||phase>=samples.Count)
                throw new ArgumentException("active_epoch_snapshot_totals_mismatch");
            return nearest?samples[phase].Nearest[(int)cohort]:
                samples[phase].Strict[(int)cohort];
        }
        internal void Report(string arm)
        {
            for(int p=0;p<samples.Count;p++)
            {
                foreach(bool isNearest in new[]{false,true})
                {
                    foreach(Cohort cohort in Enum.GetValues<Cohort>())
                    {
                        var value=Read(p,cohort,isNearest);
                        Console.WriteLine("C545D_GIO_ACTIVE_SOURCE_EPOCH_COHORT,"+
                            $"arm={arm},phase={Names[p]},"+
                            $"model={(isNearest?"nearest":"strict")},category={cohort},"+
                            $"live={value.Live},request_bytes_live={value.Bytes},"+
                            "source_heap_only=1,direct_allocator_not_proven=1,release_HOLD=1");
                    }
                }
                Console.WriteLine("C545D_GIO_ACTIVE_SOURCE_EPOCH_SCOPE,"+
                    $"arm={arm},phase={Names[p]},"+
                    $"tracked_source_live={samples[p].Count},"+
                    $"tracked_request_bytes_live={samples[p].Bytes},"+
                    "comparable_worker_epoch_not_proven_by_etlx=1,release_HOLD=1");
            }
            Console.WriteLine("C545D_GIO_ACTIVE_SOURCE_EPOCH_ACCOUNTING_PASS,"+
                $"arm={arm},phases=3,models=2,categories=10,"+
                "crosschecked_generic_live_and_bytes=1,"+
                "crosscut_realloc_guard=1,global_leak_not_proven=1,release_HOLD=1");
        }
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
        var nested=Classify(new Frame[]{new("gio-2.0-0","update_registry_data"),
            new("gio-2.0-0","keys_updated")});
        Expect(nested.Cohort==Cohort.AmbiguousMultipleMethods&&
               nested.NearestKnown==Cohort.UpdateRegistryData&&nested.FirstGioExact);
        var reverse=Classify(new Frame[]{new("gio-2.0-0","keys_updated"),
            new("gio-2.0-0","update_registry_data")});
        Expect(reverse.NearestKnown==Cohort.KeysUpdated&&
               reverse.Cohort==Cohort.AmbiguousMultipleMethods);
        var helper=Classify(new Frame[]{new("gio-2.0-0","unlisted_helper"),
            new("gio-2.0-0","keys_updated")});
        Expect(helper.NearestKnown==Cohort.KeysUpdated&&!helper.FirstGioExact);
        Expect(Classify(new Frame[]{new("gio-2.0-0","update_registry_data"),
            new("gio-2.0-0","update_registry_data()")}).Cohort==Cohort.UpdateRegistryData);
        Expect(Classify(new Frame[]{new("gio-2.0-0",null)}).Cohort==
            Cohort.GioMethodUnmatched);
        Expect(Classify(new Frame[]{new("ntdll","HeapAlloc")}).Cohort==
            Cohort.NoGioFrame);
        var cohortModel=new MethodLedger();
        var cohortGeneric=new GenericHeapLifetime();
        cohortModel.Alloc(1,10,100,Cohort.UpdateRegistryData);
        cohortGeneric.Alloc(1,10,100,GenericHeapLifetime.OriginProof.VerifiedGioMethod);
        // Native move may expose Alloc(target) and Free(old) before ReAlloc.
        cohortModel.Alloc(1,20,200,Cohort.GioMethodUnmatched);
        cohortGeneric.Alloc(1,20,200,GenericHeapLifetime.OriginProof.Unresolved);
        cohortModel.Free(1,10);cohortGeneric.Free(1,10);
        cohortModel.Realloc(1,10,20,100,200);
        cohortGeneric.Realloc(1,10,20,100,200);
        var held=cohortModel.Counts(Cohort.UpdateRegistryData);
        Expect(held.Live==1&&held.Bytes==200&&held.Original==1&&
               cohortModel.Counts(Cohort.GioMethodUnmatched).Original==0);
        cohortModel.Free(1,20);cohortGeneric.Free(1,20);
        cohortModel.FinalizePending();cohortGeneric.FinalizePending();
        cohortModel.CheckAgainst(cohortGeneric);
        Expect(cohortModel.Counts(Cohort.UpdateRegistryData).Freed==1);
        // Ambiguous function stacks remain ambiguous through a move.
        var ambiguous=new MethodLedger();
        ambiguous.Alloc(4,100,0,Cohort.AmbiguousMultipleMethods);
        ambiguous.Free(4,100);
        ambiguous.Realloc(4,100,101,0,17);
        Expect(ambiguous.Counts(Cohort.AmbiguousMultipleMethods).Live==1&&
               ambiguous.Counts(Cohort.AmbiguousMultipleMethods).Bytes==17);
        ambiguous.Free(4,101);ambiguous.FinalizePending();
        Expect(ambiguous.Counts(Cohort.AmbiguousMultipleMethods).Freed==1);
        // Freed pointer reused for another method must not inherit owner.
        var reused=new MethodLedger();
        reused.Alloc(6,15,24,Cohort.KeysUpdated);
        reused.Free(6,15);
        reused.Alloc(6,15,0,Cohort.NoGioFrame);
        reused.FinalizePending();
        Expect(reused.Counts(Cohort.KeysUpdated).Freed==1&&
               reused.Counts(Cohort.NoGioFrame).Live==1);
        // Regression: nearest report MUST use distinct prefix; otherwise the
        // controller sees 20 strict lines and zero nearest lines.
        using(var captureOutput=new StringWriter())
        {
            var prior=Console.Out;
            try
            {
                Console.SetOut(captureOutput);
                var display=new MethodLedger();
                display.Alloc(7,1,11,Cohort.KeysUpdated);
                display.Report("synthetic",nearest:true);
            }
            finally{Console.SetOut(prior);}
            var lines=captureOutput.ToString().Split('\n',
                StringSplitOptions.RemoveEmptyEntries);
            Expect(lines.Length==10 &&
                   lines.All(x=>x.StartsWith(
                       "C545D_GIO_NEAREST_METHOD_COHORT,arm=synthetic,")));
        }
        // Source owner must be inherited through ReAlloc and disappear
        // after logical Free at the third QPC cut, including the nearest
        // stack proxy while preserving strict multi-method ambiguity.
        var sourceCutGeneric=new GenericHeapLifetime();
        var sourceCutStrict=new MethodLedger();
        var sourceCutNearest=new MethodLedger();
        var sourceCuts=new ActiveEpochCuts(100,200,300);
        sourceCuts.OnHeapEvent(50,sourceCutGeneric,sourceCutStrict,sourceCutNearest);
        sourceCutGeneric.Alloc(9,1,25,GenericHeapLifetime.OriginProof.VerifiedGioMethod);
        sourceCutStrict.Alloc(9,1,25,Cohort.AmbiguousMultipleMethods);
        sourceCutNearest.Alloc(9,1,25,Cohort.UpdateRegistryData);
        sourceCuts.OnHeapEvent(150,sourceCutGeneric,sourceCutStrict,sourceCutNearest);
        Expect(sourceCuts.Read(0,Cohort.AmbiguousMultipleMethods,false).Live==1 &&
               sourceCuts.Read(0,Cohort.UpdateRegistryData,true).Bytes==25);
        sourceCuts.OnHeapEvent(175,sourceCutGeneric,sourceCutStrict,sourceCutNearest);
        sourceCutGeneric.Realloc(9,1,2,25,40);
        sourceCutStrict.Realloc(9,1,2,25,40);
        sourceCutNearest.Realloc(9,1,2,25,40);
        sourceCuts.OnHeapEvent(250,sourceCutGeneric,sourceCutStrict,sourceCutNearest);
        Expect(sourceCuts.Read(1,Cohort.UpdateRegistryData,true).Bytes==40);
        sourceCuts.OnHeapEvent(260,sourceCutGeneric,sourceCutStrict,sourceCutNearest);
        sourceCutGeneric.Free(9,2);
        sourceCutStrict.Free(9,2);
        sourceCutNearest.Free(9,2);
        sourceCuts.OnHeapEvent(350,sourceCutGeneric,sourceCutStrict,sourceCutNearest);
        sourceCuts.Finish(sourceCutGeneric,sourceCutStrict,sourceCutNearest);
        Expect(sourceCuts.Read(2,Cohort.UpdateRegistryData,true).Live==0);
        sourceCutGeneric.FinalizePending();
        sourceCutStrict.FinalizePending();
        sourceCutNearest.FinalizePending();
        sourceCutStrict.CheckAgainst(sourceCutGeneric);
        sourceCutNearest.CheckAgainst(sourceCutGeneric);
        bool crosscutRejected=false,missingTraceRejected=false;
        var crossing=new MethodLedger();
        crossing.Alloc(5,10,25,Cohort.KeysUpdated);
        crossing.Free(5,10);
        crossing.MarkEpochCut();
        try{crossing.Realloc(5,10,11,25,40);}
        catch(ArgumentException ex) when(ex.Message=="cohort_realloc_crosses_epoch_cut")
        {crosscutRejected=true;}
        try
        {
            var missing=new ActiveEpochCuts(100,200,300);
            missing.OnHeapEvent(150,new GenericHeapLifetime(),
                new MethodLedger(),new MethodLedger());
            missing.Finish(new GenericHeapLifetime(),
                new MethodLedger(),new MethodLedger());
        }
        catch(ArgumentException ex) when(ex.Message=="active_epoch_first_cut_not_inside_trace")
        {missingTraceRejected=true;}
        Expect(crosscutRejected&&missingTraceRejected);
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
            "positive=12,negative=12,method_cohort_ledger=1,"+
            "multiple_distinct_methods_ambiguous=1,realloc_target_owner_preserved=1,"+
            "active_epoch_source_cut_model=1,cutoff_crossing_rejected=1,"+
            "LFH_not_owner=1,original_stack_survives_realloc_free=1,"+
            "real_GIO_stacks_not_yet_examined=1,release_HOLD=1");
    }

    private static int Capture(string[] a)
    {
        bool activeMode=a.Length==15;
        if((a.Length!=9&&!activeMode)||a[0]!="--etl"||a[2]!="--pid"||
           a[4]!="--build"||a[6]!="--arm"||
           a[8]!="--preinit-losszero-and-pdb-match-verified")
            throw new ArgumentException("invalid_census_parameters");
        ActiveEpochCuts? cuts=null;
        if(activeMode)
        {
            if(a[9]!="--qpc-baseline"||a[11]!="--qpc-cycle1"||
               a[13]!="--qpc-cycle2"||
               !long.TryParse(a[10],NumberStyles.None,CultureInfo.InvariantCulture,out long q0)||
               !long.TryParse(a[12],NumberStyles.None,CultureInfo.InvariantCulture,out long q1)||
               !long.TryParse(a[14],NumberStyles.None,CultureInfo.InvariantCulture,out long q2))
                throw new ArgumentException("active_epoch_qpc_parameters_invalid");
            cuts=new ActiveEpochCuts(q0,q1,q2);
        }
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
        diagnosticStage="etlx_open";
        var model=new GenericHeapLifetime();
        var methodLedger=new MethodLedger();
        var nearestLedger=new MethodLedger();
        int nearestFirstGioRaw=0;
        currentLifetime=model;
        countAlloc=countRealloc=countFree=missingStacks=hasGioFrameCount=exactMethodCount=loadedGioModules=lookupModules=0;
        countZeroAlloc=countZeroRealloc=countZeroOldSize=countZeroNewSize=0;
        int heapAlloc=0,heapEvents=0,heapRealloc=0,heapFree=0;
        int missingStack=0,hasGioModule=0,exactMethod=0,unknownOrigin=0;
        int orphanRealloc=0,orphanFree=0;
        int moduleCandidates=0,exactModulePdbLookups=0;
        using(var log=TraceLog.OpenOrConvert(etl,new TraceLogOptions{ConversionLog=TextWriter.Null}))
        {
            diagnosticStage="process_lookup";
            var process=log.Processes.LastProcessWithID(pid);
            if(process is null)throw new ArgumentException("selected_process_metadata_absent");
            diagnosticStage="native_module_symbol_lookup";
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
                    loadedGioModules=moduleCandidates;
                    log.CodeAddresses.LookupSymbolsForModule(reader,m.ModuleFile);
                    exactModulePdbLookups++;
                    lookupModules=exactModulePdbLookups;
                }
            }
            diagnosticStage="heap_event_replay";
            using(var src=log.Events.GetSource())
            {
                var heap=new HeapTraceProviderTraceEventParser(src);
                void Tick(long eventQpc)
                {
                    if(++heapEvents>EventCap)
                        throw new ArgumentException("heap_event_capture_limit");
                    cuts?.OnHeapEvent(eventQpc,model,methodLedger,nearestLedger);
                }
                heap.HeapTraceAlloc+=ev=>
                {
                    if(ev.ProcessID!=pid)return;
                    Tick(ev.TimeStampQPC);heapAlloc++;countAlloc=heapAlloc;
                    if(ev.AllocSize==0)countZeroAlloc++;
                    // Valid non-null HeapAlloc(0) can still own an allocated
                    // heap block. The shared lifetime model validates heap
                    // handle/address and rejects negative or unbounded size.
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
                    missingStacks=missingStack;
                    hasGioFrameCount=hasGioModule;
                    exactMethodCount=exactMethod;
                    model.Alloc(ev.HeapHandle,ev.AllocAddress,ev.AllocSize,
                        result.ExactGioMethod
                        ? GenericHeapLifetime.OriginProof.VerifiedGioMethod
                        : GenericHeapLifetime.OriginProof.Unresolved);
                    methodLedger.Alloc(ev.HeapHandle,ev.AllocAddress,ev.AllocSize,
                        result.Cohort);
                    nearestLedger.Alloc(ev.HeapHandle,ev.AllocAddress,ev.AllocSize,
                        result.NearestKnown);
                    if(result.FirstGioExact)nearestFirstGioRaw++;
                };
                heap.HeapTraceReAlloc+=ev=>
                {
                    if(ev.ProcessID!=pid)return;
                    Tick(ev.TimeStampQPC);heapRealloc++;countRealloc=heapRealloc;
                    if(ev.OldAllocSize==0)countZeroOldSize++;
                    if(ev.NewAllocSize==0)countZeroNewSize++;
                    if(ev.OldAllocSize==0 || ev.NewAllocSize==0)countZeroRealloc++;
                    if(model.IsTracked(ev.HeapHandle,ev.OldAllocAddress))
                    {
                        model.Realloc(ev.HeapHandle,ev.OldAllocAddress,
                            ev.NewAllocAddress,ev.OldAllocSize,ev.NewAllocSize);
                        methodLedger.Realloc(ev.HeapHandle,ev.OldAllocAddress,
                            ev.NewAllocAddress,ev.OldAllocSize,ev.NewAllocSize);
                        nearestLedger.Realloc(ev.HeapHandle,ev.OldAllocAddress,
                            ev.NewAllocAddress,ev.OldAllocSize,ev.NewAllocSize);
                    }
                    else orphanRealloc++;
                };
                heap.HeapTraceFree+=ev=>
                {
                    if(ev.ProcessID!=pid)return;
                    Tick(ev.TimeStampQPC);heapFree++;countFree=heapFree;
                    if(model.IsTracked(ev.HeapHandle,ev.FreeAddress))
                    {
                        model.Free(ev.HeapHandle,ev.FreeAddress);
                        methodLedger.Free(ev.HeapHandle,ev.FreeAddress);
                        nearestLedger.Free(ev.HeapHandle,ev.FreeAddress);
                    }
                    else orphanFree++;
                };
                src.Process();
            }
        }
        diagnosticStage="finalize_owner_lifetime";
        // In the gated active mode the capture fence is required to stop
        // ETW after the second process QPC checkpoint.
        cuts?.Finish(model,methodLedger,nearestLedger);
        model.FinalizePending();
        methodLedger.FinalizePending();
        nearestLedger.FinalizePending();
        methodLedger.CheckAgainst(model);
        nearestLedger.CheckAgainst(model);
        var snapshot=model.Snapshot();
        methodLedger.Report(arm);
        nearestLedger.Report(arm,nearest:true);
        cuts?.Report(arm);
        Console.WriteLine($"C545D_GIO_NEAREST_FRAME_SCOPE,arm={arm},"+
            $"raw_first_gio_exact_method={nearestFirstGioRaw},"+
            "raw_not_logical_owner_count=1,release_HOLD=1");
        diagnosticStage="safe_numeric_census";
        Console.WriteLine($"C545D_GIO_ETLX_FIRST_SOURCE_CENSUS,arm={arm},"+
            $"pid_heap_events={heapEvents},original_alloc_events={heapAlloc},"+
            $"zero_req_original_alloc={countZeroAlloc},"+
            $"zero_req_realloc={countZeroRealloc},"+
            $"zero_req_old_size={countZeroOldSize},zero_req_new_size={countZeroNewSize},"+
            "zero_req_not_zero_heap_commit=1,"+
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
        catch(ArgumentException ex)
        {
            string reason=SafeArgumentReasons.Contains(ex.Message)
                ?ex.Message:"source_history_or_symbol_scope_unverified";
            Console.WriteLine("C545D_GIO_ETLX_FIRST_SOURCE_GAP,"+
                "reason="+reason+Diagnostic()+",raw_uploaded=0,release_HOLD=1");
            return 2;
        }
        catch(Exception)
        {
            Console.WriteLine("C545D_GIO_ETLX_FIRST_SOURCE_GAP,"+
                "reason=ETLX_decode_or_symbol_resolution_unverified"+
                Diagnostic()+",raw_uploaded=0,release_HOLD=1");
            return 3;
        }
    }
}
