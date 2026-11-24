// v0.4 development candidate. Optional diagnostics; not approved for installation.
// One background worker; no PowerShell scriptblock is invoked on another thread.
using System;
using System.Collections.Concurrent;
using System.Threading;
using System.IO;
using System.Text;
using System.Globalization;
using System.Collections.Generic;
using System.Text.RegularExpressions;

public sealed class C545DMetadataWriterV04 {
    const int Capacity=16;
    readonly BlockingCollection<C545DMetadataJournalV04.Row> queue=
        new BlockingCollection<C545DMetadataJournalV04.Row>(Capacity);
    readonly string root;
    readonly string receiptRoot;
    string receiptStatus="not_enabled";
    readonly Thread worker;
    long accepted, rejected, saved, recovered, failed;
    int stopping;
    // Single publication owner calls TryPublish and Stop serially, as in actual namer loop.
    public C545DMetadataWriterV04(string trustedRoot,string trustedReceiptRoot){
        root=trustedRoot;receiptRoot=trustedReceiptRoot;
        worker=new Thread(Run);worker.IsBackground=true;worker.Name="C545D diagnostic journal";
        worker.Start();
    }
    public string TryPublish(C545DMetadataJournalV04.Row row){
        // Deep-copy fixed value fields: caller mutation cannot change queued evidence.
        // Only fixed allowlisted status values; never retain arbitrary strings.
        if(row==null||!(row.Status=="profile_match_metadata_only"||row.Status=="profile_mismatch"||
            row.Status=="invalid_metadata"||row.Status=="probe_unavailable"||row.Status=="probe_failed")){
            Interlocked.Increment(ref rejected);return "invalid_row";
        }
        var copy=new C545DMetadataJournalV04.Row{
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
        C545DWriterReceipts.Ticket ticket=null;
        if(receiptRoot!=null){
            ticket=C545DWriterReceipts.Start(receiptRoot,DateTime.UtcNow);
            Volatile.Write(ref receiptStatus,ticket==null?"start_unavailable":"started_not_final");
        }
        foreach(var row in queue.GetConsumingEnumerable()){
            try{
                string status=C545DMetadataJournalV04.AppendRecovering(root,row);
                if(status=="saved"||status=="saved_after_recovery"){
                    Interlocked.Increment(ref saved);
                    if(status=="saved_after_recovery")Interlocked.Increment(ref recovered);
                }else Interlocked.Increment(ref failed);
            }catch{Interlocked.Increment(ref failed);}
        }
        if(ticket!=null){
            bool ok=C545DWriterReceipts.Finish(ticket,DateTime.UtcNow,Accepted,Rejected,Saved,Failed,Recovered);
            Volatile.Write(ref receiptStatus,ok?"final_saved":"final_unconfirmed");
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
    public string ReceiptStatus { get { return Volatile.Read(ref receiptStatus); } }
}


// CI-only bounded per-writer-run receipts. Start written before consumption;
// final written only after complete queue drain. No caller-side disk IO.
// Never fabricate counters for a run without a valid final record.
// No directory enumeration. 128 slots * 1024 bytes, completed slots eligible
// for reuse after 32 days; unfinished/corrupt slots preserved (capacity loss
// visible as unavailable receipt, not a promise of total run coverage).
public static class C545DWriterReceipts {
    const int Slots=128, Limit=1024;
    static readonly CultureInfo Inv=CultureInfo.InvariantCulture;
    static readonly Encoding Ascii=Encoding.GetEncoding(20127,EncoderFallback.ExceptionFallback,DecoderFallback.ExceptionFallback);
    const string Stamp="yyyyMMdd'T'HHmmss.fffffff'Z'";
    public sealed class Ticket { internal string Path, Token; internal DateTime Start; }
    public sealed class Entry {
        public DateTime StartUtc, EndUtc;
        public bool Final;
        public long Accepted=-1, Rejected=-1, Saved=-1, Failed=-1, Recovered=-1;
        internal string Token;
    }
    public sealed class Snapshot {
        public string Status="coverage_unverified";
        public int InvalidSlots, BusySlots, UnfinishedRuns, CompletedRuns;
        // Capacity snapshot independent of requested report dates, not a reservation.
        public int EmptySlots, ReusableSlots, RecentFinalSlots, PreservedUnfinishedSlots;
        public bool CapacityObserved;
        public List<Entry> Rows=new List<Entry>();
    }
    static bool ValidTime(DateTime t){return t.Kind==DateTimeKind.Utc&&t.Year>=2020&&t.Year<=2100;}
    static bool SafeRoot(string root){
        if(String.IsNullOrEmpty(root)||!Regex.IsMatch(root,@"^[A-Za-z]:\\"))return false;
        var d=new DirectoryInfo(Path.GetFullPath(root));
        if(new DriveInfo(d.Root.FullName).DriveType!=DriveType.Fixed)return false;
        while(d!=null){if(!d.Exists||(d.Attributes&FileAttributes.ReparsePoint)!=0)return false;d=d.Parent;}
        return true;
    }
    static string PathAt(string root,int i){return Path.Combine(root,"writer_"+i.ToString("D3",Inv)+".dat");}
    static string Time(DateTime t){return t.ToString(Stamp,Inv);}
    static DateTime ParseTime(string s){
        var t=DateTime.ParseExact(s,Stamp,Inv,DateTimeStyles.AssumeUniversal|DateTimeStyles.AdjustToUniversal);
        if(!ValidTime(t)||Time(t)!=s)throw new InvalidDataException();return t;
    }
    static string Header(Entry r){return "C545D_WRITER_V1|"+Time(r.StartUtc)+"|"+r.Token+"\n";}
    static string FinalLine(Entry r){
        if(!ValidTime(r.EndUtc)||r.EndUtc<r.StartUtc||r.Accepted<0||r.Rejected<0||r.Saved<0||r.Failed<0||r.Recovered<0||
           r.Saved>r.Accepted||r.Failed!=r.Accepted-r.Saved||r.Recovered>r.Saved)throw new InvalidDataException();
        return String.Join("|",new[]{"END",Time(r.EndUtc),r.Accepted.ToString(Inv),r.Rejected.ToString(Inv),
            r.Saved.ToString(Inv),r.Failed.ToString(Inv),r.Recovered.ToString(Inv)})+"\n";
    }
    static Entry Read(FileStream f){
        if(f.Length<=0||f.Length>Limit)throw new InvalidDataException();
        var b=new byte[(int)f.Length];int n=0;while(n<b.Length){int k=f.Read(b,n,b.Length-n);if(k==0)throw new EndOfStreamException();n+=k;}
        var lines=Ascii.GetString(b).Split('\n');
        if((lines.Length!=2&&lines.Length!=3)||lines[lines.Length-1]!="")throw new InvalidDataException();
        var h=lines[0].Split('|');
        if(h.Length!=3||h[0]!="C545D_WRITER_V1"||!Regex.IsMatch(h[2],@"\A[0-9a-f]{32}\z"))throw new InvalidDataException();
        var r=new Entry{StartUtc=ParseTime(h[1]),Token=h[2]};
        if(Header(r)!=lines[0]+"\n")throw new InvalidDataException();
        if(lines.Length==3){
            var e=lines[1].Split('|');if(e.Length!=7||e[0]!="END")throw new InvalidDataException();
            r.Final=true;r.EndUtc=ParseTime(e[1]);r.Accepted=Int64.Parse(e[2],Inv);r.Rejected=Int64.Parse(e[3],Inv);
            r.Saved=Int64.Parse(e[4],Inv);r.Failed=Int64.Parse(e[5],Inv);r.Recovered=Int64.Parse(e[6],Inv);
            if(FinalLine(r)!=lines[1]+"\n")throw new InvalidDataException();
        }
        return r;
    }
    static void Write(FileStream f,string text){
        byte[] b=Ascii.GetBytes(text);if(f.Position+b.Length>Limit)throw new InvalidDataException();
        f.Write(b,0,b.Length);f.Flush(true);
    }
    public static Ticket Start(string root,DateTime now){
        if(!ValidTime(now))return null;
        try{
            if(!SafeRoot(root))return null;
            for(int i=0;i<Slots;i++){
                string p=PathAt(root,i);
                try{
                    bool exists=File.Exists(p);
                    if(exists&&(File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0)continue;
                    using(var f=File.Open(p,exists?FileMode.Open:FileMode.CreateNew,FileAccess.ReadWrite,FileShare.None)){
                        if(exists){
                            var old=Read(f);
                            if(!old.Final||old.EndUtc>now.AddDays(-32))continue;
                            f.SetLength(0);f.Position=0;
                        }
                        var r=new Entry{StartUtc=now,Token=Guid.NewGuid().ToString("N")};
                        Write(f,Header(r));return new Ticket{Path=p,Token=r.Token,Start=now};
                    }
                }catch{/* slot unavailable or invalid: preserve, never delete */}
            }
        }catch{}
        return null;
    }
    public static bool Finish(Ticket t,DateTime end,long accepted,long rejected,long saved,long failed,long recovered){
        if(t==null)return false;
        try{
            if(!SafeRoot(Path.GetDirectoryName(t.Path))||(File.GetAttributes(t.Path)&FileAttributes.ReparsePoint)!=0)return false;
            using(var f=File.Open(t.Path,FileMode.Open,FileAccess.ReadWrite,FileShare.None)){
                var r=Read(f);if(r.Final||r.Token!=t.Token||r.StartUtc!=t.Start)return false;
                r.Final=true;r.EndUtc=end;r.Accepted=accepted;r.Rejected=rejected;r.Saved=saved;r.Failed=failed;r.Recovered=recovered;
                string line=FinalLine(r);f.Position=f.Length;Write(f,line);return true;
            }
        }catch{return false;}
    }
    public static Snapshot ReadWindow(string root,DateTime begin,DateTime end){
        var s=new Snapshot();
        if(!ValidTime(begin)||!ValidTime(end)||end<=begin||(end-begin).TotalDays>31){s.Status="window_invalid";return s;}
        try{
            if(!SafeRoot(root)){s.Status="root_rejected";return s;}
            DateTime observed=DateTime.UtcNow;
            for(int i=0;i<Slots;i++){
                string p=PathAt(root,i);
                try{
                    // File.Exists can hide access failures; only FileNotFound is empty.
                    FileAttributes attrs;
                    try{attrs=File.GetAttributes(p);}
                    catch(FileNotFoundException){s.EmptySlots++;continue;}
                    if((attrs&(FileAttributes.ReparsePoint|FileAttributes.Directory))!=0){s.InvalidSlots++;continue;}
                    using(var f=File.Open(p,FileMode.Open,FileAccess.Read,FileShare.Read)){
                        var r=Read(f);
                        if(!r.Final)s.PreservedUnfinishedSlots++;
                        else if(r.EndUtc<=observed.AddDays(-32))s.ReusableSlots++;
                        else s.RecentFinalSlots++;
                        // Whole-run totals, NOT attributed to individual report-window events.
                        if(r.StartUtc>=end||(r.Final&&r.EndUtc<begin))continue;
                        if(r.Final)s.CompletedRuns++;else s.UnfinishedRuns++;
                        r.Token=null;s.Rows.Add(r);
                    }
                }catch(InvalidDataException){s.InvalidSlots++;}
                 catch(FormatException){s.InvalidSlots++;}
                 catch(OverflowException){s.InvalidSlots++;}
                 catch(DecoderFallbackException){s.InvalidSlots++;}
                 catch(IOException){s.BusySlots++;}
                 catch{s.InvalidSlots++;}
            }
            s.CapacityObserved=(s.EmptySlots+s.ReusableSlots+s.RecentFinalSlots+s.PreservedUnfinishedSlots+s.InvalidSlots+s.BusySlots==Slots);
            if(s.InvalidSlots>0||s.BusySlots>0||s.UnfinishedRuns>0)s.Status="partial_or_unavailable";
            else if(s.Rows.Count==0)s.Status="no_runs_coverage_unverified";
            return s;
        }catch{s.Status="storage_error";s.Rows.Clear();return s;}
    }
}
