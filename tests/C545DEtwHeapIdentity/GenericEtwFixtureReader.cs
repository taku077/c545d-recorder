// Disposable Windows CI only. Reads an actual mixed-size native ETW fixture;
// deliberately leaves source ownership UNRESOLVED until a trusted allocation
// call-stack/module proof is implemented. No pointers, PID, process paths,
// registry strings, stack frames or raw ETL ever appear in logged output.
using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Diagnostics.Tracing;
using Microsoft.Diagnostics.Tracing.Parsers.Kernel;

internal static class GenericEtwFixtureReader
{
    private static GenericHeapLifetime? lastModel;
    private static int[] countsDiagnostic=new int[3];
    private static int lastPidEvents;
    private static int lastEarlyMarker;
    private static readonly HashSet<string> SafeReasons = new()
    {
        "invalid_generic_fixture_cli","disposable_windows_ci_only",
        "private_runner_missing","nonprivate_trace_path","missing_or_unbounded_trace",
        "invalid_owned_native_fixture_pid","too_many_fixture_heap_events",
        "nonunique_fixture_size_source","mixed_realloc_source_size_wrong",
        "mixed_fixture_counts_or_precleanup_marker_missing",
        "mixed_fixture_not_fully_freed_or_unpaired",
        "unbounded_heap_event_stream","invalid_heap_event_identity_or_size",
        "unverified_original_stack_source","overlapping_live_allocation",
        "orphan_realloc_prior_alloc_not_observed",
        "stale_provisional_free_cannot_match_realloc",
        "realloc_old_size_does_not_match","realloc_new_address_collision",
        "invalid_free_identity","duplicate_provisional_free",
        "orphan_free_or_stale_realloc_address","trace_scope_or_loss_unverified",
        "expected_model_event_types_missing"
    };
    private static string Diagnostic()
    {
        var m=lastModel;
        var p=m?.Snapshot();
        return $",events_from_selected_pid={lastPidEvents},"+
               $"count192={countsDiagnostic[0]},count448={countsDiagnostic[1]},"+
               $"count832={countsDiagnostic[2]},precleanup_held6={lastEarlyMarker},"+
               $"observed_original_alloc={m?.AllocCount ?? 0},"+
               $"observed_linked_realloc={m?.ReallocCount ?? 0},"+
               $"observed_realloc_old_free_pair={m?.ReallocOldFreeMatched ?? 0},"+
               $"observed_pending_free={m?.PendingFreeCount ?? 0},"+
               $"observed_live_count={p?.Count ?? 0},"+
               $"observed_live_bytes={p?.Bytes ?? 0}";
    }
    private static readonly HashSet<long> InitialSizes = new(){192,448,832};
    private static readonly Dictionary<long,long> ReallocSizes =
        new(){{192,544},{448,1216},{832,1800}};
    private static int Run(string[] args)
    {
        if(args.Length!=5 || args[0]!="--generic-fixture-etl" ||
           args[2]!="--pid" || args[4]!="--preworkload-and-losszero-verified")
            throw new ArgumentException("invalid_generic_fixture_cli");
        if(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")!="true" ||
           Environment.GetEnvironmentVariable("RUNNER_OS")!="Windows")
            throw new ArgumentException("disposable_windows_ci_only");
        string? parent=Environment.GetEnvironmentVariable("RUNNER_TEMP");
        if(string.IsNullOrWhiteSpace(parent))
            throw new ArgumentException("private_runner_missing");
        string path=Path.GetFullPath(args[1]);
        string fullParent=Path.GetFullPath(parent);
        if(!path.StartsWith(fullParent+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("nonprivate_trace_path");
        var info=new FileInfo(path);
        if(!info.Exists || info.Length<512 || info.Length>128*1024*1024)
            throw new ArgumentException("missing_or_unbounded_trace");
        if(!int.TryParse(args[3],out int pid) || pid<=0)
            throw new ArgumentException("invalid_owned_native_fixture_pid");

        var model=new GenericHeapLifetime();
        lastModel=model;countsDiagnostic=new int[3];lastPidEvents=0;lastEarlyMarker=0;
        var counts=new Dictionary<long,int>{{192,0},{448,0},{832,0}};
        int original=0,heapEvents=0,unrelatedAlloc=0,unrelatedRealloc=0,unrelatedFree=0;
        int matched=0,earlyMarker=0;
        using(var source=new ETWTraceEventSource(path))
        {
            var heap=new HeapTraceProviderTraceEventParser(source);
            void CheckMilestone()
            {
                var snapshot=model.Snapshot();
                if(model.AllocCount==24 && model.ReallocCount==6 &&
                   snapshot.Count==6 &&
                   model.FreeCount+model.PendingFreeCount==18 &&
                   snapshot.Bytes==7120)
                    earlyMarker=1;
                lastEarlyMarker=earlyMarker;
            }
            heap.HeapTraceAlloc+=evt =>
            {
                if(evt.ProcessID!=pid)return;
                lastPidEvents=++heapEvents;
                if(heapEvents>100000)throw new ArgumentException("too_many_fixture_heap_events");
                long size=evt.AllocSize;
                if(!InitialSizes.Contains(size))
                {
                    model.ObserveUntrackedAlloc(evt.HeapHandle,evt.AllocAddress,size);
                    unrelatedAlloc++;CheckMilestone();return;
                }
                // The shape (3 sizes * 8 allocations) is only used to
                // test our generic parser, NOT to attribute real GIO origin.
                counts[size]++;
                countsDiagnostic[size==192?0:size==448?1:2]=counts[size];
                if(counts[size]>8)throw new ArgumentException("nonunique_fixture_size_source");
                model.Alloc(evt.HeapHandle,evt.AllocAddress,size,
                            GenericHeapLifetime.OriginProof.Unresolved);
                original++;
                CheckMilestone();
            };
            heap.HeapTraceReAlloc+=evt =>
            {
                if(evt.ProcessID!=pid)return;
                lastPidEvents=++heapEvents;
                if(heapEvents>100000)throw new ArgumentException("too_many_fixture_heap_events");
                if(!model.IsTracked(evt.HeapHandle,evt.OldAllocAddress))
                {
                    model.ObserveUntrackedRealloc(evt.HeapHandle,evt.OldAllocAddress,
                        evt.NewAllocAddress,evt.OldAllocSize,evt.NewAllocSize);
                    unrelatedRealloc++;CheckMilestone();return;
                }
                if(!ReallocSizes.TryGetValue(evt.OldAllocSize,out long expected) ||
                   evt.NewAllocSize!=expected)
                    throw new ArgumentException("mixed_realloc_source_size_wrong");
                model.Realloc(evt.HeapHandle,evt.OldAllocAddress,
                              evt.NewAllocAddress,evt.OldAllocSize,evt.NewAllocSize);
                matched++;
                CheckMilestone();
            };
            heap.HeapTraceFree+=evt =>
            {
                if(evt.ProcessID!=pid)return;
                lastPidEvents=++heapEvents;
                if(heapEvents>100000)throw new ArgumentException("too_many_fixture_heap_events");
                if(model.IsTracked(evt.HeapHandle,evt.FreeAddress))
                {
                    model.Free(evt.HeapHandle,evt.FreeAddress);
                    CheckMilestone();
                }
                else
                {
                    model.ObserveUntrackedFree(evt.HeapHandle,evt.FreeAddress);
                    unrelatedFree++;
                    CheckMilestone();
                }
            };
            source.Process();
        }
        if(original!=24 || matched!=6 || earlyMarker!=1 ||
           counts[192]!=8 || counts[448]!=8 || counts[832]!=8)
            throw new ArgumentException("mixed_fixture_counts_or_precleanup_marker_missing");
        model.FinalizePending();
        var snapshot=model.Snapshot();
        if(snapshot.Count!=0 || snapshot.Bytes!=0 || model.FreeCount!=24 ||
           model.ReallocCount!=6 || model.ReallocOldFreeMatched!=6)
            throw new ArgumentException("mixed_fixture_not_fully_freed_or_unpaired");
        string summary=model.Summary(true,true,true);
        Console.WriteLine(summary+
            $",fixture_observed_alloc192={counts[192]},"+
            $"fixture_observed_alloc448={counts[448]},"+
            $"fixture_observed_alloc832={counts[832]},"+
            $"fixture_precleanup_held6={earlyMarker},"+
            $"mixed_selected_pid_events={heapEvents},"+
            $"unrelated_alloc={unrelatedAlloc},"+
            $"unrelated_realloc={unrelatedRealloc},"+
            $"unrelated_free={unrelatedFree},"+
            "new_mixed_size_real_ETW_reader_pass=1,"+
            "owner_stack_source_classification_proven=0,"+
            "preworkload_losszero_controller_gated=1,"+
            "synthetic_native_fixture_only=1");
        return 0;
    }
    internal static int MainMode(string[] args)
    {
        try{return Run(args);}
        catch(ArgumentException ex)
        {
            string reason=SafeReasons.Contains(ex.Message)?ex.Message:"source_or_lifetime_unverified";
            Console.WriteLine("C545D_ETW_GENERIC_HEAP_GAP,reason="+reason+
                              Diagnostic()+
                              ",raw_uploaded=0,real_GIO_owner_unproven=1,release_HOLD=1");
            return 2;
        }
        catch(Exception)
        {
            Console.WriteLine("C545D_ETW_GENERIC_HEAP_GAP,reason=etw_decode_unverified"+
                              Diagnostic()+
                              ",raw_uploaded=0,real_GIO_owner_unproven=1,release_HOLD=1");
            return 3;
        }
    }
}
