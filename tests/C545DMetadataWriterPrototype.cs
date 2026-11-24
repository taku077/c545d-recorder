// CI-only: fixed-capacity diagnostic writer; no disk IO on publication caller.
// One background worker; no PowerShell scriptblock is invoked on another thread.
using System;
using System.Collections.Concurrent;
using System.Threading;

public sealed class C545DMetadataWriterPrototype {
    const int Capacity=16;
    readonly BlockingCollection<C545DMetadataJournalPrototype.Row> queue=
        new BlockingCollection<C545DMetadataJournalPrototype.Row>(Capacity);
    readonly string root;
    readonly ManualResetEventSlim fixtureGate; // CI-only artificial disk stall
    readonly Thread worker;
    long accepted, rejected, saved, recovered, failed;
    int stopping;
    public C545DMetadataWriterPrototype(string trustedRoot,ManualResetEventSlim syntheticGate){
        root=trustedRoot;fixtureGate=syntheticGate;
        worker=new Thread(Run);worker.IsBackground=true;worker.Name="C545D diagnostic journal CI";
        worker.Start();
    }
    public string TryPublish(C545DMetadataJournalPrototype.Row row){
        // Deep-copy fixed value fields: caller mutation cannot change queued evidence.
        // Only fixed allowlisted status values; never retain arbitrary strings.
        if(row==null||!(row.Status=="profile_match_metadata_only"||row.Status=="profile_mismatch"||
            row.Status=="invalid_metadata"||row.Status=="probe_unavailable"||row.Status=="probe_failed")){
            Interlocked.Increment(ref rejected);return "invalid_row";
        }
        var copy=new C545DMetadataJournalPrototype.Row{
            Utc=row.Utc,Status=row.Status,DurationMs=row.DurationMs,VideoTracks=row.VideoTracks,
            AudioTracks=row.AudioTracks,Width=row.Width,Height=row.Height,FpsNum=row.FpsNum,FpsDen=row.FpsDen,
            SampleRate=row.SampleRate,Channels=row.Channels,H264=row.H264,Aac=row.Aac};
        if(Volatile.Read(ref stopping)!=0){Interlocked.Increment(ref rejected);return "stopping";}
        try{
            if(queue.TryAdd(copy,0)){Interlocked.Increment(ref accepted);return "queued_not_saved";}
            Interlocked.Increment(ref rejected);return "queue_full";
        }catch(InvalidOperationException){Interlocked.Increment(ref rejected);return "stopping";}
    }
    void Run(){
        foreach(var row in queue.GetConsumingEnumerable()){
            try{
                if(fixtureGate!=null)fixtureGate.Wait();
                string status=C545DMetadataJournalPrototype.AppendRecovering(root,row);
                if(status=="saved"||status=="saved_after_recovery"){
                    Interlocked.Increment(ref saved);
                    if(status=="saved_after_recovery")Interlocked.Increment(ref recovered);
                }else Interlocked.Increment(ref failed);
            }catch{Interlocked.Increment(ref failed);}
        }
    }
    // Does not cancel an in-flight disk operation or block recorder indefinitely.
    // A false result means the caller must report unconfirmed diagnostic drain.
    // The worker remains alive to finish; never create a replacement worker on timeout.
    public bool Stop(int timeoutMs){
        if(timeoutMs<0||timeoutMs>5000)throw new ArgumentOutOfRangeException("timeoutMs");
        if(Interlocked.Exchange(ref stopping,1)==0)queue.CompleteAdding();
        return worker.Join(timeoutMs);
    }
    public long Accepted { get { return Interlocked.Read(ref accepted); } }
    public long Rejected { get { return Interlocked.Read(ref rejected); } }
    public long Saved { get { return Interlocked.Read(ref saved); } }
    public long Recovered { get { return Interlocked.Read(ref recovered); } }
    public long Failed { get { return Interlocked.Read(ref failed); } }
    public int Pending { get { return queue.Count; } }
}
