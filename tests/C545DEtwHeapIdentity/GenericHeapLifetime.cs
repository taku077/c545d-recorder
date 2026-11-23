// Size-independent per-PID ETW HeapAlloc -> HeapReAlloc -> HeapFree model.
// NEVER infer GIO ownership from size, heap handle, PID, stack group, or
// allocator source (lookaside/LFH/main path). A separate positive call-stack
// proof is required to elevate OriginProof.Unknown to a real source.
// The model cannot establish a fully quiet GIO/APC/WinRT epoch by itself.
using System;
using System.Collections.Generic;
using System.Linq;

internal sealed class GenericHeapLifetime
{
    internal enum OriginProof { Unresolved = 0, SyntheticFixture = 1, VerifiedGioMethod = 2 }

    private readonly record struct Key(ulong Heap, ulong Address);
    private readonly record struct Block(long Bytes, OriginProof Proof, long Birth, int Reallocations);
    private readonly record struct Pending(Block Value, long FreeSeq);

    private readonly Dictionary<Key, Block> live = new();
    private readonly Dictionary<Key, Pending> pending = new();
    private long seq;
    internal int GioMethodOriginalAllocations { get; private set; }
    internal int GioMethodLinkedReallocations { get; private set; }
    internal int GioMethodLogicalFrees { get; private set; }
    internal int ProvenOriginalAllocations { get; private set; }
    internal int ProvenReallocationOrigins { get; private set; }
    internal int ProvenLogicalFrees { get; private set; }
    internal int ZeroRequestedOriginalAllocations { get; private set; }
    internal int ZeroRequestedReallocations { get; private set; }
    internal int AllocCount { get; private set; }
    internal int ReallocCount { get; private set; }
    internal int FreeCount { get; private set; }
    internal int ReallocOldFreeMatched { get; private set; }
    internal int ReallocTargetPreallocated { get; private set; }
    internal int MaxPreallocTargetEventGap { get; private set; }
    internal int ReallocMoved { get; private set; }
    internal int ReallocInplace { get; private set; }
    internal int AddressReuse { get; private set; }
    internal int ReuseByUntrackedSource { get; private set; }
    internal int MaxFreeReallocGap { get; private set; }
    private const long MaxSize = 1L << 36;
    private const long MaxEvents = 2_000_000;
    private const long MaxReallocGap = 32;

    private void Tick()
    {
        if (++seq > MaxEvents)
            throw new ArgumentException("unbounded_heap_event_stream");
    }
    private static void Check(ulong heap, ulong address, long size)
    {
        if (heap == 0 || address == 0 || size < 0 || size > MaxSize)
            throw new ArgumentException("invalid_heap_event_identity_or_size");
    }

    internal void Alloc(ulong heap, ulong address, long size, OriginProof proof)
    {
        Tick();
        Check(heap,address,size);
        if (!Enum.IsDefined(proof))
            throw new ArgumentException("unverified_original_stack_source");
        var key = new Key(heap,address);
        if (live.ContainsKey(key))
            throw new ArgumentException("overlapping_live_allocation");
        // If the allocator truly reused a freed address, the old object
        // cannot subsequently be reassigned to a ReAlloc event. Any such
        // later event fails closed as an orphan.
        if (pending.Remove(key,out var retired))
        {
            FreeCount++;
            if(retired.Value.Proof==OriginProof.SyntheticFixture)ProvenLogicalFrees++;
            if(retired.Value.Proof==OriginProof.VerifiedGioMethod)GioMethodLogicalFrees++;
            AddressReuse++;
        }
        live.Add(key,new Block(size,proof,seq,0));
        AllocCount++;
        if(size==0)ZeroRequestedOriginalAllocations++;
        if(proof==OriginProof.SyntheticFixture)ProvenOriginalAllocations++;
        if(proof==OriginProof.VerifiedGioMethod)GioMethodOriginalAllocations++;
    }

    internal void Realloc(ulong heap, ulong oldAddress, ulong newAddress,
                          long oldSize, long newSize)
    {
        Tick();
        Check(heap,oldAddress,oldSize);
        Check(heap,newAddress,newSize);
        var before = new Key(heap,oldAddress);
        var after = new Key(heap,newAddress);
        bool wasLive = live.TryGetValue(before,out var original);
        if (!wasLive)
        {
            if (!pending.TryGetValue(before,out var saved))
                throw new ArgumentException("orphan_realloc_prior_alloc_not_observed");
            long gap=seq-saved.FreeSeq;
            if (gap < 1 || gap > MaxReallocGap)
                throw new ArgumentException("stale_provisional_free_cannot_match_realloc");
            MaxFreeReallocGap=Math.Max(MaxFreeReallocGap,(int)gap);
            original=saved.Value;
        }
        if (original.Bytes!=oldSize)
            throw new ArgumentException("realloc_old_size_does_not_match");
        // A real Windows heap may expose HeapAlloc(newAddress) BEFORE
        // HeapReAlloc(oldAddress,newAddress) for the very same move.
        // Do not discard arbitrary collisions: only pair the exact heap,
        // exact new size, fresh destination, no previous realloc/free,
        // and bounded preceding-event distance.
        bool preallocated=false;
        Block target=default!;
        if(after!=before)
        {
            if(pending.ContainsKey(after))
                throw new ArgumentException("realloc_target_was_already_freed");
            if(live.TryGetValue(after,out target))
            {
                long targetAge=seq-target.Birth;
                if(target.Bytes!=newSize || target.Reallocations!=0 ||
                   targetAge<1 || targetAge>MaxReallocGap)
                    throw new ArgumentException("preallocated_realloc_target_unverified");
                preallocated=true;
            }
        }
        if(preallocated)
        {
            if(!live.Remove(after))
                throw new ArgumentException("realloc_new_address_disappeared");
            ReallocTargetPreallocated++;
            MaxPreallocTargetEventGap=Math.Max(MaxPreallocTargetEventGap,
                (int)(seq-target.Birth));
            // The internal target HeapAlloc is not a SECOND original
            // logical owner; the old address's proven original origin wins.
            if(target.Proof==OriginProof.SyntheticFixture)ProvenOriginalAllocations--;
            if(target.Proof==OriginProof.VerifiedGioMethod)GioMethodOriginalAllocations--;
        }
        if (wasLive) live.Remove(before);
        else
        {
            pending.Remove(before);
            ReallocOldFreeMatched++;
        }
        live.Add(after,new Block(newSize,original.Proof,original.Birth,
                                 original.Reallocations+1));
        ReallocCount++;
        if(oldSize==0 || newSize==0)ZeroRequestedReallocations++;
        if(original.Proof==OriginProof.SyntheticFixture)ProvenReallocationOrigins++;
        if(original.Proof==OriginProof.VerifiedGioMethod)GioMethodLinkedReallocations++;
        if (oldAddress==newAddress) ReallocInplace++; else ReallocMoved++;
    }

    internal void Free(ulong heap,ulong address)
    {
        Tick();
        if (heap==0 || address==0)
            throw new ArgumentException("invalid_free_identity");
        var key=new Key(heap,address);
        if (pending.ContainsKey(key))
            throw new ArgumentException("duplicate_provisional_free");
        if (!live.Remove(key,out var value))
            throw new ArgumentException("orphan_free_or_stale_realloc_address");
        pending.Add(key,new Pending(value,seq));
    }

    // A provisionally freed block is already absent from live. This
    // finalization is permitted only at a trustworthy observation cut,
    // never used to guess a subsequent ReAlloc owner from absent history.
    internal void FinalizePending()
    {
        FreeCount=checked(FreeCount+pending.Count);
        foreach(var item in pending.Values)
        {
            if(item.Value.Proof==OriginProof.SyntheticFixture)ProvenLogicalFrees++;
            if(item.Value.Proof==OriginProof.VerifiedGioMethod)GioMethodLogicalFrees++;
        }
        pending.Clear();
    }

    // An event from a size class not included in a controlled fixture may
    // reuse the address of a formerly freed *selected* block. Consume
    // its retired identity; NEVER attribute the new allocation to the
    // previous owner. Full GIO census must instead track all sizes.
    internal void ObserveUntrackedAlloc(ulong heap,ulong address,long size)
    {
        Tick();
        Check(heap,address,size);
        var key=new Key(heap,address);
        if (live.ContainsKey(key))
            throw new ArgumentException("foreign_allocation_overlaps_selected_live");
        if (pending.Remove(key,out var retired))
        {
            FreeCount++;
            if(retired.Value.Proof==OriginProof.SyntheticFixture)ProvenLogicalFrees++;
            if(retired.Value.Proof==OriginProof.VerifiedGioMethod)GioMethodLogicalFrees++;
            AddressReuse++;
            ReuseByUntrackedSource++;
        }
    }

    internal void ObserveUntrackedRealloc(ulong heap,ulong oldAddress,
                                          ulong newAddress,long oldSize,long newSize)
    {
        Tick();
        Check(heap,oldAddress,oldSize);
        Check(heap,newAddress,newSize);
        var oldKey=new Key(heap,oldAddress);
        var newKey=new Key(heap,newAddress);
        if (live.ContainsKey(oldKey) || pending.ContainsKey(oldKey) ||
            live.ContainsKey(newKey))
            throw new ArgumentException("untracked_realloc_overlaps_selected_identity");
        if (pending.Remove(newKey,out var retired))
        {
            FreeCount++;
            if(retired.Value.Proof==OriginProof.SyntheticFixture)ProvenLogicalFrees++;
            if(retired.Value.Proof==OriginProof.VerifiedGioMethod)GioMethodLogicalFrees++;
            AddressReuse++;
            ReuseByUntrackedSource++;
        }
    }

    internal void ObserveUntrackedFree(ulong heap,ulong address)
    {
        Tick();
        if(heap==0 || address==0)
            throw new ArgumentException("invalid_untracked_free");
        if(IsTracked(heap,address))
            throw new ArgumentException("free_of_selected_address_not_accounted");
    }

    internal bool IsTracked(ulong heap, ulong address)
    {
        return live.ContainsKey(new Key(heap,address)) ||
               pending.ContainsKey(new Key(heap,address));
    }

    internal int PendingFreeCount => pending.Count;

    internal (int Count,long Bytes,int Reallocated,int Unresolved) Snapshot()
    {
        long bytes=0;
        int realloc=0,unresolved=0;
        foreach(var b in live.Values)
        {
            bytes=checked(bytes+b.Bytes);
            if(b.Reallocations>0)realloc++;
            if(b.Proof==OriginProof.Unresolved)unresolved++;
        }
        return (live.Count,bytes,realloc,unresolved);
    }

    internal string Summary(bool completeOriginCapture, bool lossZero,
                            bool sourceEpochAcknowledged)
    {
        var snap=Snapshot();
        if (!completeOriginCapture || !lossZero)
            throw new ArgumentException("trace_scope_or_loss_unverified");
        if (AllocCount<=0 || ReallocCount<=0)
            throw new ArgumentException("expected_model_event_types_missing");
        // Even if synthetically source-acknowledged, a WinRT/GLib close is
        // never implied. Production gate remains HOLD unconditionally.
        return "C545D_ETW_GENERIC_HEAP_LIFETIME,"+
            $"observed_original_alloc={AllocCount},linked_realloc={ReallocCount},"+
            $"zero_requested_original_alloc={ZeroRequestedOriginalAllocations},"+
            $"zero_requested_realloc={ZeroRequestedReallocations},"+
            "zero_request_never_equated_to_zero_committed_bytes=1,"+
            $"fixture_proven_original_alloc={ProvenOriginalAllocations},"+
            $"gio_method_original_alloc={GioMethodOriginalAllocations},"+
            $"gio_method_realloc={GioMethodLinkedReallocations},"+
            $"gio_method_freed={GioMethodLogicalFrees},"+
            $"fixture_proven_origin_realloc={ProvenReallocationOrigins},"+
            $"fixture_proven_origin_freed={ProvenLogicalFrees},"+
            $"finalized_free={FreeCount},live_count={snap.Count},"+
            $"live_request_bytes={snap.Bytes},reallocated_live={snap.Reallocated},"+
            $"unresolved_origin_live={snap.Unresolved},"+
            $"pending_free_unfinalized={pending.Count},"+
            $"old_free_before_realloc_matched={ReallocOldFreeMatched},"+
            $"realloc_moved={ReallocMoved},realloc_inplace={ReallocInplace},"+
            $"internal_preallocated_realloc_targets={ReallocTargetPreallocated},"+
            $"max_target_alloc_to_realloc_event_gap={MaxPreallocTargetEventGap},"+
            $"logical_original_alloc_estimate={AllocCount-ReallocTargetPreallocated},"+
            $"max_free_realloc_event_gap={MaxFreeReallocGap},"+
            $"address_reuse_after_free={AddressReuse},"+
            $"reuse_from_untracked_size={ReuseByUntrackedSource},"+
            $"fixture_source_epoch_ack={Convert.ToInt32(sourceEpochAcknowledged)},"+
            "real_GIO_source_owner_proven=0,global_appinfo_quiet_proven=0,"+
            "real_device_tested=0,release_HOLD=1,raw_addresses_uploaded=0";
    }

    internal static void SelfTest()
    {
        static void Expect(bool condition){if(!condition)throw new InvalidOperationException("fixture_assertion_failed");}
        var a=new GenericHeapLifetime();
        var sizes=new long[]{192,448,832,2048,16384,37};
        for(int i=0;i<sizes.Length;i++)
            a.Alloc(9,(ulong)i+1,sizes[i],
                i%2==0?OriginProof.SyntheticFixture:OriginProof.Unresolved);
        // Both realloc styles; a Free event may precede ReAlloc.
        a.Free(9,1);
        a.Realloc(9,1,101,192,544);
        a.Realloc(9,2,2,448,1216);
        a.Free(9,3);
        a.Free(9,4);
        a.Free(9,5);
        a.Free(9,6);
        var held=a.Snapshot();
        Expect(held.Count==2 && held.Bytes==1760 && held.Reallocated==2 &&
               held.Unresolved==1 && a.ReallocOldFreeMatched==1);
        a.Free(9,101);a.Free(9,2);
        a.FinalizePending();
        var done=a.Snapshot();
        Expect(done.Count==0 && done.Bytes==0 && a.FreeCount==6 &&
               a.ReallocCount==2 && a.AllocCount==6);
        Expect(a.Summary(true,true,true).Contains("live_count=0"));
        Expect(a.ProvenOriginalAllocations==3 && a.ProvenReallocationOrigins==1 &&
               a.ProvenLogicalFrees==3);
        // A reused address starts a new allocation epoch; cannot be
        // used later as evidence for the old object's reallocation.
        var reused=new GenericHeapLifetime();
        reused.Alloc(7,1,68,OriginProof.Unresolved);
        reused.Free(7,1);
        reused.Alloc(7,1,900,OriginProof.Unresolved);
        Expect(reused.AddressReuse==1);
        // Address reuse by a different-sized native allocation must
        // not invent a new owner or report a false double free.
        var reusedOther=new GenericHeapLifetime();
        reusedOther.Alloc(7,33,192,OriginProof.SyntheticFixture);
        reusedOther.Free(7,33);
        reusedOther.ObserveUntrackedAlloc(7,33,2000);
        reusedOther.ObserveUntrackedFree(7,33);
        reusedOther.FinalizePending();
        Expect(reusedOther.FreeCount==1 &&
               reusedOther.ReuseByUntrackedSource==1 &&
               reusedOther.ProvenLogicalFrees==1 &&
               reusedOther.Snapshot().Count==0);
        // HeapAlloc(0) can return a real address with a valid lifetime.
        // 0 is a REQUEST size, not a proof that the heap used no pages.
        var zero=new GenericHeapLifetime();
        zero.Alloc(3,501,0,OriginProof.VerifiedGioMethod);
        var z0=zero.Snapshot();
        Expect(z0.Count==1 && z0.Bytes==0 && z0.Unresolved==0 &&
               zero.ZeroRequestedOriginalAllocations==1);
        zero.Free(3,501); // Native Free may arrive before ReAlloc.
        zero.Realloc(3,501,502,0,32);
        zero.Realloc(3,502,502,32,0); // size can become zero again.
        Expect(zero.Snapshot().Count==1 &&
               zero.GioMethodLinkedReallocations==2 &&
               zero.ZeroRequestedReallocations==2);
        zero.Free(3,502);
        zero.FinalizePending();
        Expect(zero.Snapshot().Count==0 && zero.FreeCount==1 &&
               zero.GioMethodOriginalAllocations==1 &&
               zero.GioMethodLogicalFrees==1);
        var zeroOther=new GenericHeapLifetime();
        zeroOther.Alloc(4,201,0,OriginProof.Unresolved);
        zeroOther.Free(4,201);
        zeroOther.Alloc(4,201,0,OriginProof.Unresolved); // reuse still recognized
        Expect(zeroOther.AddressReuse==1 && zeroOther.FreeCount==1 &&
               zeroOther.Snapshot().Count==1 && zeroOther.Snapshot().Bytes==0);
        var gioOnly=new GenericHeapLifetime();
        gioOnly.Alloc(11,51,4096,OriginProof.VerifiedGioMethod);
        gioOnly.Free(11,51);
        gioOnly.Realloc(11,51,52,4096,8192);
        gioOnly.Free(11,52);
        gioOnly.FinalizePending();
        Expect(gioOnly.GioMethodOriginalAllocations==1 &&
               gioOnly.GioMethodLinkedReallocations==1 &&
               gioOnly.GioMethodLogicalFrees==1 &&
               gioOnly.ProvenOriginalAllocations==0);
        // Real ETW ordering candidate: Alloc(new) and Free(old) are
        // seen BEFORE HeapReAlloc. Proven original owner must survive;
        // internal Alloc(new) must not invent an extra original owner.
        var targetFirst=new GenericHeapLifetime();
        targetFirst.Alloc(99,10,350,OriginProof.VerifiedGioMethod);
        targetFirst.Alloc(99,20,900,OriginProof.Unresolved);
        targetFirst.Free(99,10);
        targetFirst.Realloc(99,10,20,350,900);
        targetFirst.Free(99,20);
        targetFirst.FinalizePending();
        Expect(targetFirst.GioMethodOriginalAllocations==1 &&
               targetFirst.GioMethodLinkedReallocations==1 &&
               targetFirst.GioMethodLogicalFrees==1 &&
               targetFirst.ReallocTargetPreallocated==1 &&
               targetFirst.FreeCount==1 &&
               targetFirst.Snapshot().Count==0);
        Action[] bad={
            () => new GenericHeapLifetime().Alloc(0,1,100,OriginProof.Unresolved),
            () => new GenericHeapLifetime().Alloc(1,0,100,OriginProof.Unresolved),
            () => new GenericHeapLifetime().Alloc(1,1,-1,OriginProof.Unresolved),
            () => new GenericHeapLifetime().Alloc(1,1,100,(OriginProof)9),
            () => {var t=new GenericHeapLifetime();t.Alloc(1,0,0,OriginProof.Unresolved);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,0,OriginProof.Unresolved);t.Realloc(1,1,2,0,-1);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.Alloc(1,1,100,OriginProof.Unresolved);},
            () => new GenericHeapLifetime().Realloc(1,1,2,100,200),
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.Realloc(1,1,2,99,200);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.Alloc(1,2,100,OriginProof.Unresolved);t.Realloc(1,1,2,100,200);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.Free(1,1);t.Free(1,1);},
            () => new GenericHeapLifetime().Free(1,888),
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.Free(1,1);for(int i=0;i<33;i++)t.Alloc(1,100+(ulong)i,1000,OriginProof.Unresolved);t.Realloc(1,1,3,100,200);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.Realloc(1,1,2,100,200);t.Free(1,1);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.Realloc(1,1,2,100,200);t.Summary(false,true,true);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.Realloc(1,1,2,100,200);t.Summary(true,false,true);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.Free(1,1);t.FinalizePending();t.Realloc(1,1,2,100,200);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.ObserveUntrackedAlloc(1,1,200);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.ObserveUntrackedRealloc(1,2,1,80,200);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);t.ObserveUntrackedFree(1,1);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);
                  t.Alloc(1,2,210,OriginProof.Unresolved);t.Realloc(1,1,2,100,200);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);
                  t.Alloc(1,2,200,OriginProof.Unresolved);t.Free(1,2);
                  t.Realloc(1,1,2,100,200);},
            () => {var t=new GenericHeapLifetime();t.Alloc(1,1,100,OriginProof.Unresolved);
                  t.Alloc(1,2,200,OriginProof.Unresolved);
                  for(int z=0;z<33;z++)t.Alloc(1,(ulong)(100+z),50,OriginProof.Unresolved);
                  t.Realloc(1,1,2,100,200);},
        };
        for (int i=0;i<bad.Length;i++)
        {
            bool denied=false;
            try {bad[i]();}
            catch (ArgumentException) {denied=true;}
            Expect(denied);
        }
        Console.WriteLine("C545D_ETW_GENERIC_HEAP_SELFTEST_PASS,positive=7,negative=23,"+
            "arbitrary_sizes=1,zero_request_identity_tracked=1,"+
            "zero_request_not_zero_commit=1,source_class_no_size_guess=1,orphan_realloc_denied=1,"+
            "source_gio_untested=1,release_HOLD=1,raw_addresses_uploaded=0");
    }
}
