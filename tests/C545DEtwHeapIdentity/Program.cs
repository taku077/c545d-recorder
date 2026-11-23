// CI-only exact heap identity reader. Never prints a pointer, heap handle,
// process ID, raw ETL line, stack frame, process path, or exception text.
// The selected fixture is native: 64 HeapAlloc(360), 16 HeapReAlloc(720),
// 48 HeapFree before trace stop, 16 intentionally live, not a leak.
// For real GIO, additional proof of preworkload capture and producer-close
// is mandatory; this program deliberately rejects non-synthetic use.
using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Diagnostics.Tracing;
using Microsoft.Diagnostics.Tracing.Parsers;
using Microsoft.Diagnostics.Tracing.Parsers.Kernel;

internal static class Program
{
    private sealed class GapException : Exception
    {
        internal GapException(string reason) : base(reason) { }
    }

    private sealed record Block(long Size, int Reallocations);
    private sealed class IdentityTracker
    {
        private readonly Dictionary<(ulong Heap, ulong Address), Block> live = new();
        // On this WPT build the old block emits a HeapFree event BEFORE
        // HeapReAlloc(old,new). Defer classifying an observed free as an
        // application free until a matching realloc can consume it.
        private readonly Dictionary<(ulong Heap, ulong Address), (Block Value, int Sequence)> pendingFree = new();
        private int sequence;
        internal int RawSelectedFree { get; private set; }
        internal int ReallocAfterFree { get; private set; }
        internal int MaxFreeReallocDistance { get; private set; }
        internal int OriginalAlloc { get; private set; }
        internal int Realloc { get; private set; }
        internal int Freed => pendingFree.Count;
        internal int Moved { get; private set; }
        internal int Inplace { get; private set; }
        internal int OtherRealloc { get; private set; }
        internal int OtherFree { get; private set; }
        internal int UnrelatedAlloc { get; private set; }
        internal bool PrecleanupHeldMilestone { get; private set; }

        private void ObservePrecleanupMilestone()
        {
            // Only a known native fixture promises no extra allocations
            // after its ready-to-cleanup signal. Do not generalize to GIO.
            if (OriginalAlloc==64 && Realloc==16 && RawSelectedFree==64 &&
                pendingFree.Count==48 && live.Count==16)
                PrecleanupHeldMilestone=true;
        }

        internal void OnAlloc(ulong heap, ulong addr, long bytes)
        {
            sequence++;
            if (bytes != 360)
            {
                UnrelatedAlloc++;
                return;
            }
            if (heap == 0 || addr == 0 || pendingFree.ContainsKey((heap,addr)) ||
                !live.TryAdd((heap,addr), new Block(bytes, 0)))
                throw new GapException("duplicate_or_invalid_original_address");
            OriginalAlloc++;
            if (OriginalAlloc > 64)
                throw new GapException("ambiguous_original_360_allocations");
        }

        internal void OnRealloc(ulong heap, ulong oldAddress, ulong newAddress,
                                long oldBytes, long newBytes)
        {
            sequence++;
            var fromLive=live.TryGetValue((heap,oldAddress),out Block? prior);
            if(!fromLive)
            {
                if (!pendingFree.TryGetValue((heap,oldAddress),out var pending))
                {
                    OtherRealloc++;
                    return;
                }
                int distance=sequence-pending.Sequence;
                if (distance<1 || distance>32)
                    throw new GapException("free_to_realloc_sequence_not_local");
                MaxFreeReallocDistance=Math.Max(MaxFreeReallocDistance,distance);
                prior=pending.Value;
                pendingFree.Remove((heap,oldAddress));
                ReallocAfterFree++;
            }
            if (heap == 0 || oldAddress == 0 || newAddress == 0 ||
                prior is null || prior.Size != oldBytes || newBytes != 720)
                throw new GapException("realloc_identity_or_size_mismatch");
            if (oldAddress != newAddress && (live.ContainsKey((heap, newAddress)) ||
                    pendingFree.ContainsKey((heap,newAddress))))
                throw new GapException("realloc_target_collision");
            if (fromLive && !live.Remove((heap,oldAddress)))
                throw new GapException("realloc_old_address_missing");
            live.Add((heap,newAddress), new Block(newBytes, prior.Reallocations + 1));
            Realloc++;
            if (oldAddress == newAddress) Inplace++; else Moved++;
            if (Realloc > 16)
                throw new GapException("realloc_count_exceeded_fixture");
            ObservePrecleanupMilestone();
        }

        internal void OnFree(ulong heap, ulong address)
        {
            sequence++;
            if (live.Remove((heap,address), out var prior))
            {
                RawSelectedFree++;
                if (!pendingFree.TryAdd((heap,address),(prior,sequence)))
                    throw new GapException("duplicate_provisional_free");
            }
            else if (pendingFree.ContainsKey((heap,address)))
            {
                throw new GapException("duplicated_selected_address_free");
            }
            else
            {
                // Other native-runtime allocations can predate tracing.
                // An unknown free must never be assigned to this fixture.
                OtherFree++;
            }
            ObservePrecleanupMilestone();
        }

        internal (int Live, long Bytes, int ReallocatedLive) Snapshot()
        {
            int converted=0;
            long bytes=0;
            foreach (var b in live.Values)
            {
                bytes=checked(bytes+b.Size);
                if (b.Reallocations > 0) converted++;
            }
            return (live.Count, bytes, converted);
        }

        internal string Diagnostics(int events)
        {
            var snap=Snapshot();
            return $",events_from_pid={events},observed_360_alloc={OriginalAlloc},"+
                   $"observed_linked_realloc={Realloc},observed_linked_free={Freed},"+
                   $"observed_held_count={snap.Live},observed_held_bytes={snap.Bytes},"+
                   $"observed_raw_selected_free={RawSelectedFree},"+
                   $"observed_realloc_after_free={ReallocAfterFree},"+
                   $"observed_max_free_realloc_distance={MaxFreeReallocDistance},"+
                   $"observed_pending_true_free={pendingFree.Count},"+
                   $"observed_precleanup_held_milestone={intMode(PrecleanupHeldMilestone)},"+
                   $"observed_reallocated_held_count={snap.ReallocatedLive},"+
                   $"observed_realloc_moved={Moved},observed_realloc_inplace={Inplace},"+
                   $"unrelated_realloc={OtherRealloc},unrelated_free={OtherFree},"+
                   $"unrelated_alloc={UnrelatedAlloc}";
        }

        private static int intMode(bool x) => x ? 1 : 0;

        internal string Validate(bool expectThroughCleanup=false)
        {
            var snap = Snapshot();
            if (OriginalAlloc != 64 || Realloc != 16 || Moved + Inplace != 16 ||
                !PrecleanupHeldMilestone || 
                (expectThroughCleanup
                  ? Freed != 64 || RawSelectedFree != 80 || snap.Live != 0 ||
                    snap.Bytes != 0 || snap.ReallocatedLive != 0
                  : Freed != 48 || RawSelectedFree != 64 || snap.Live != 16 ||
                    snap.Bytes != 11520 || snap.ReallocatedLive != 16))
                throw new GapException("known_fixture_alloc_realloc_free_counts_not_reconciled");
            return "C545D_ETW_REALLOC_IDENTITY_MATCHED,"+
                $"original_alloc={OriginalAlloc},realloc={Realloc},tracked_free={Freed},"+
                $"held_at_trace_stop={snap.Live},held_bytes={snap.Bytes},"+
                $"precleanup_held_milestone={intMode(PrecleanupHeldMilestone)},"+
                $"postcleanup_free_verified={intMode(expectThroughCleanup)},"+
                $"realloc_moved={Moved},realloc_inplace={Inplace},"+
                $"raw_selected_free={RawSelectedFree},realloc_after_provisional_free={ReallocAfterFree},"+
                $"max_provisional_free_to_realloc_event_distance={MaxFreeReallocDistance},"+
                $"unrelated_alloc_events={UnrelatedAlloc},"+
                $"unrelated_realloc_events={OtherRealloc},unrelated_free_events={OtherFree},"+
                "original_address_identity_preserved=1,"+
                $"expected_lifetime_deliberately_held={intMode(!expectThroughCleanup)},"+
                $"post_epoch_free_observed={intMode(expectThroughCleanup)},"+
                "global_GIO_APC_WinRT_producer_closed_proven=0,"+
                "real_GIO_original_owner_proven=0,real_GIO_tested=0,"+
                "leak_proven=0,raw_addresses_uploaded=0,real_host_untouched=1";
        }
    }

    private static void Require(bool ok, string code)
    {
        if (!ok) throw new GapException(code);
    }

    private static void Test()
    {
        var tracked = new IdentityTracker();
        for (ulong i=1;i<=64;i++) tracked.OnAlloc(101,i,360);
        for (ulong i=49;i<=64;i++)
            tracked.OnRealloc(101,i,1000+i,360,720);
        for (ulong i=1;i<=48;i++) tracked.OnFree(101,i);
        Require(tracked.Validate().Contains("held_at_trace_stop=16"),"fixture_positive_failed");
        var inplace=new IdentityTracker();
        for(ulong i=1;i<=64;i++) inplace.OnAlloc(101,i,360);
        for(ulong i=49;i<=64;i++) inplace.OnRealloc(101,i,i,360,720);
        for(ulong i=1;i<=48;i++) inplace.OnFree(101,i);
        Require(inplace.Validate().Contains("realloc_inplace=16"),"fixture_inplace_failed");
        // Exact native ETW ordering measured on the original private Windows
        // fixture: a HeapFree for the old address precedes the HeapReAlloc.
        // The provisional free must NOT erase its HeapAlloc origin.
        var prefree=new IdentityTracker();
        for(ulong i=1;i<=64;i++) prefree.OnAlloc(101,i,360);
        for(ulong i=49;i<=64;i++)
        {
            prefree.OnFree(101,i);
            prefree.OnRealloc(101,i,1000+i,360,720);
        }
        for(ulong i=1;i<=48;i++)prefree.OnFree(101,i);
        Require(prefree.Validate().Contains("realloc_after_provisional_free=16"),
                "native_free_before_realloc_fixture_failed");
        // Same 64/16/48 fixture, but extend the event stream through
        // the explicit final 16 frees. The former 16 outstanding vanish.
        for(ulong i=49;i<=64;i++)prefree.OnFree(101,1000+i);
        Require(prefree.Validate(expectThroughCleanup:true).Contains("postcleanup_free_verified=1"),
                "native_final_cleanup_fixture_failed");
        var negative=new List<Action>
        {
            () => {var t=new IdentityTracker(); t.OnAlloc(1,1,360);t.OnAlloc(1,1,360);},
            () => {var t=new IdentityTracker();t.OnAlloc(1,1,360);t.OnRealloc(1,1,2,359,720);},
            () => {var t=new IdentityTracker();t.OnAlloc(1,1,360);t.OnAlloc(1,2,360);t.OnRealloc(1,1,2,360,720);},
            () => {var t=new IdentityTracker();t.OnAlloc(1,1,360);t.OnRealloc(1,1,0,360,720);},
            () => {var t=new IdentityTracker();t.OnAlloc(1,1,360);t.OnRealloc(1,1,2,360,719);},
            () => {var t=new IdentityTracker();t.Validate();},
            () => {var t=new IdentityTracker();for(ulong i=1;i<=65;i++)t.OnAlloc(1,i,360);},
            () => {var t=new IdentityTracker();t.OnAlloc(1,1,360);t.OnFree(1,1);t.Validate();},
            () => {var t=new IdentityTracker();t.OnAlloc(1,0,360);},
            () => {var t=new IdentityTracker();t.OnAlloc(1,1,360);t.OnFree(1,1);t.OnFree(1,1);},
            () => {var t=new IdentityTracker();t.OnAlloc(1,1,360);t.OnFree(1,1);t.OnAlloc(1,1,360);},
            () => {var t=new IdentityTracker();t.OnAlloc(1,1,360);t.OnFree(1,1);
                for(int z=0;z<35;z++)t.OnAlloc(1,1000UL+(ulong)z,100);
                t.OnRealloc(1,1,100,360,720);},
            () => {var t=new IdentityTracker();t.Validate(expectThroughCleanup:true);},
        };
        for(int i=0;i<negative.Count;i++)
        {
            bool rejected=false;
            try { negative[i](); } catch(GapException) { rejected=true; }
            Require(rejected,"negative_fixture_wrongly_accepted");
        }
        Console.WriteLine("C545D_ETW_REALLOC_IDENTITY_SELFTEST_PASS,positive=4,negative=13,provisional_free_before_realloc=1,pointers_exposed=0,real_ETL_parsed=0,host_untouched=1");
    }

    private static int Main(string[] args)
    {
        IdentityTracker? diagnosticTracker = null;
        int diagnosticEventCount = 0;
        try
        {
            if (args.Length==1 && args[0]=="--selftest")
            {
                Test();
                return 0;
            }
            bool expectThroughCleanup=(args.Length==6 && args[5]=="--expect-through-cleanup");
            if ((args.Length!=5 && !expectThroughCleanup) ||
                args[0]!="--etl" || args[2]!="--pid" ||
                args[4]!="--preworkload-and-losszero-verified")
                throw new GapException("invalid_cli_or_trace_gates");
            Require(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")=="true" &&
                    Environment.GetEnvironmentVariable("RUNNER_OS")=="Windows",
                    "disposable_windows_ci_only");
            string? root=Environment.GetEnvironmentVariable("RUNNER_TEMP");
            Require(!string.IsNullOrEmpty(root),"CI_private_directory_missing");
            string path=Path.GetFullPath(args[1]);
            string fullRoot=Path.GetFullPath(root!);
            Require(path.StartsWith(fullRoot+Path.DirectorySeparatorChar,
                StringComparison.OrdinalIgnoreCase), "ETL_not_under_private_runner_temp");
            Require(int.TryParse(args[3],out int pid)&&pid>0,"invalid_owned_pid");
            var fi=new FileInfo(path);
            Require(fi.Exists && fi.Length>=512 && fi.Length<=128*1024*1024,
                    "ETL_absent_or_unbounded");
            var tracker=new IdentityTracker();
            diagnosticTracker=tracker;
            int pidEvents=0;
            using(var source=new ETWTraceEventSource(path))
            {
                var heap=new HeapTraceProviderTraceEventParser(source);
                heap.HeapTraceAlloc += data =>
                {
                    if (data.ProcessID!=pid) return;
                    pidEvents++;
                    diagnosticEventCount=pidEvents;
                    tracker.OnAlloc(data.HeapHandle,data.AllocAddress,data.AllocSize);
                };
                heap.HeapTraceReAlloc += data =>
                {
                    if(data.ProcessID!=pid) return;
                    pidEvents++;
                    diagnosticEventCount=pidEvents;
                    tracker.OnRealloc(data.HeapHandle,data.OldAllocAddress,
                            data.NewAllocAddress,data.OldAllocSize,data.NewAllocSize);
                };
                heap.HeapTraceFree += data =>
                {
                    if(data.ProcessID!=pid) return;
                    pidEvents++;
                    diagnosticEventCount=pidEvents;
                    tracker.OnFree(data.HeapHandle,data.FreeAddress);
                };
                source.Process();
            }
            Require(pidEvents>=128 && pidEvents<=250000,"heap_events_missing_or_excessive");
            Console.WriteLine(tracker.Validate(expectThroughCleanup)+
                $",heap_events_from_selected_pid={pidEvents},"+
                "preworkload_barrier_verified_by_controller=1,"+
                "logger_loss_zero_verified_by_controller=1,"+
                "actual_ETW_event_adapter=1,synthetic_fixture_only=1");
            return 0;
        }
        catch(GapException ex)
        {
            // Ex.Message is strictly one of the internal closed enum strings.
            Console.WriteLine($"C545D_ETW_REALLOC_IDENTITY_GAP,reason={ex.Message}"+
                (diagnosticTracker?.Diagnostics(diagnosticEventCount) ?? "")+
                ",raw_uploaded=0,release_HOLD=1");
            return 2;
        }
        catch(Exception)
        {
            Console.WriteLine("C545D_ETW_REALLOC_IDENTITY_GAP,reason=unrecognized_ETL_or_parser_failure"+
                (diagnosticTracker?.Diagnostics(diagnosticEventCount) ?? "")+
                ",raw_uploaded=0,release_HOLD=1");
            return 3;
        }
    }
}
