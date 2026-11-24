// CI-only bounded metadata event journal. No media access, raw paths or arbitrary JSON.
// Trusted private local root, no concurrent adversarial namespace mutations.
// 32 UTC-day slots, max 256 records/day, 64 KiB/slot; no enumeration or deletion.
using System;
using System.IO;
using System.Text;
using System.Globalization;
using System.Collections.Generic;
using System.Text.RegularExpressions;

public static class C545DMetadataJournalPrototype {
    const int Days=32, MaxRows=256, MaxBytes=65536;
    static readonly CultureInfo Inv=CultureInfo.InvariantCulture;
    static readonly DateTime Epoch=new DateTime(2020,1,1,0,0,0,DateTimeKind.Utc);
    const string Stamp="yyyyMMdd'T'HHmmss.fffffff'Z'";
    static readonly Encoding Ascii=Encoding.GetEncoding(20127,EncoderFallback.ExceptionFallback,DecoderFallback.ExceptionFallback);
    public sealed class Row {
        public DateTime Utc;
        public string Status;
        public long DurationMs;
        public int VideoTracks, AudioTracks, Width, Height, FpsNum, FpsDen, SampleRate, Channels, H264, Aac;
    }
    public sealed class Snapshot {
        public string Status="coverage_unverified";
        public int InvalidSlots, BusySlots, SaturatedSlots, RecoveredSlots;
        public List<Row> Rows=new List<Row>();
    }
    static bool IsDay(DateTime t) { return t.Kind==DateTimeKind.Utc && t>=Epoch && t.Year<=2100; }
    static int Slot(DateTime t){return (t.Date-Epoch).Days%Days;}
    static string PathFor(string root,int slot){return Path.Combine(root,"metadata_"+slot.ToString("D2",Inv)+".dat");}
    static bool SafeRoot(string root) {
        if(String.IsNullOrEmpty(root)||!Regex.IsMatch(root,@"^[A-Za-z]:\\"))return false;
        var d=new DirectoryInfo(Path.GetFullPath(root));
        if(new DriveInfo(d.Root.FullName).DriveType!=DriveType.Fixed)return false;
        while(d!=null){if(!d.Exists||(d.Attributes&FileAttributes.ReparsePoint)!=0)return false;d=d.Parent;}
        return true;
    }
    static bool Valid(Row r){
        if(r==null||!IsDay(r.Utc)||r.DurationMs < -1||r.DurationMs>86400000||r.DurationMs==0)return false;
        if(r.Status!="profile_match_metadata_only"&&r.Status!="profile_mismatch"&&r.Status!="invalid_metadata"&&r.Status!="probe_unavailable"&&r.Status!="probe_failed")return false;
        if(r.VideoTracks < -1||r.VideoTracks>16||r.AudioTracks < -1||r.AudioTracks>16)return false;
        foreach(int n in new[]{r.Width,r.Height,r.FpsNum,r.FpsDen,r.SampleRate,r.Channels})if(n < -1||n>999999999||n==0)return false;
        if(r.H264 < -1||r.H264>1||r.Aac < -1||r.Aac>1)return false;
        if(r.Status=="profile_match_metadata_only")
            return r.VideoTracks==1&&r.AudioTracks==1&&r.Width==2560&&r.Height==720&&r.FpsNum>0&&r.FpsDen>0&&
                (long)r.FpsNum==15L*r.FpsDen&&r.SampleRate==48000&&r.Channels==1&&r.H264==1&&r.Aac==1&&r.DurationMs>0;
        return true;
    }
    static string Encode(Row r){
        if(!Valid(r))throw new InvalidDataException();
        return String.Join("|",new[]{r.Utc.ToString(Stamp,Inv),r.Status,r.DurationMs.ToString(Inv),
            r.VideoTracks.ToString(Inv),r.AudioTracks.ToString(Inv),r.Width.ToString(Inv),r.Height.ToString(Inv),
            r.FpsNum.ToString(Inv),r.FpsDen.ToString(Inv),r.SampleRate.ToString(Inv),r.Channels.ToString(Inv),
            r.H264.ToString(Inv),r.Aac.ToString(Inv)});
    }
    static Row Decode(string line) {
        if(line.Length>256)throw new InvalidDataException();
        var s=line.Split('|');
        if(s.Length!=13)throw new InvalidDataException();
        var r=new Row{Utc=DateTime.ParseExact(s[0],Stamp,Inv,DateTimeStyles.AssumeUniversal|DateTimeStyles.AdjustToUniversal),
          Status=s[1],DurationMs=Int64.Parse(s[2],Inv),VideoTracks=Int32.Parse(s[3],Inv),AudioTracks=Int32.Parse(s[4],Inv),
          Width=Int32.Parse(s[5],Inv),Height=Int32.Parse(s[6],Inv),FpsNum=Int32.Parse(s[7],Inv),FpsDen=Int32.Parse(s[8],Inv),
          SampleRate=Int32.Parse(s[9],Inv),Channels=Int32.Parse(s[10],Inv),H264=Int32.Parse(s[11],Inv),Aac=Int32.Parse(s[12],Inv)};
        if(Encode(r)!=line)throw new InvalidDataException();
        return r;
    }
    static List<Row> Read(FileStream f,int slot,out bool recovered){
        recovered=false;
        if(f.Length<=0||f.Length>MaxBytes)throw new InvalidDataException();
        var bytes=new byte[(int)f.Length];int read=0;
        while(read<bytes.Length){int n=f.Read(bytes,read,bytes.Length-read);if(n==0)throw new EndOfStreamException();read+=n;}
        string text=Ascii.GetString(bytes);
        if(!text.EndsWith("\n",StringComparison.Ordinal))throw new InvalidDataException();
        string[] lines=text.Split('\n');
        if(lines.Length<3||lines.Length>MaxRows+2)throw new InvalidDataException();
        recovered=lines[0].StartsWith("C545D_META_R1|",StringComparison.Ordinal);
        string header=recovered?"C545D_META_R1|":"C545D_META_V1|";
        if(!lines[0].StartsWith(header,StringComparison.Ordinal))throw new InvalidDataException();
        var day=DateTime.ParseExact(lines[0].Substring(14),"yyyyMMdd",Inv,DateTimeStyles.AssumeUniversal|DateTimeStyles.AdjustToUniversal);
        if(!IsDay(day)||Slot(day)!=slot||lines[0]!=header+day.ToString("yyyyMMdd",Inv))throw new InvalidDataException();
        var result=new List<Row>();
        for(int i=1;i<lines.Length-1;i++){
            var r=Decode(lines[i]);if(r.Utc.Date!=day.Date)throw new InvalidDataException();result.Add(r);
        }
        return result;
    }
    public static string Append(string root,Row row){
        if(!Valid(row))return "invalid_row";
        try{
            if(!SafeRoot(root))return "root_rejected";
            string path=PathFor(root,Slot(row.Utc));
            bool exists=File.Exists(path);
            if(exists&&(File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)return "reparse_rejected";
            // Exclusive open is the cross-process gate. No retry or wait loop.
            using(var f=File.Open(path,FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None)){
                bool reset=!exists&&f.Length==0;
                if(!reset){
                    bool recovered;
                    var rows=Read(f,Slot(row.Utc),out recovered);
                    var day=rows[0].Utc.Date;
                    if(day>row.Utc.Date)return "clock_rollback";
                    reset=day<row.Utc.Date;
                    if(!reset&&rows.Count>=MaxRows)return "capacity_reached";
                }
                string text=(reset?"C545D_META_V1|"+row.Utc.ToString("yyyyMMdd",Inv)+"\n":"")+Encode(row)+"\n";
                byte[] bytes=Ascii.GetBytes(text);
                if((reset?0:f.Length)+bytes.Length>MaxBytes)return "capacity_reached";
                if(reset){f.SetLength(0);f.Position=0;}else f.Position=f.Length;
                f.Write(bytes,0,bytes.Length);f.Flush(true);
            }
            return "saved";
        }catch(InvalidDataException){return "source_invalid";}
         catch(FormatException){return "source_invalid";}
         catch(OverflowException){return "source_invalid";}
         catch(DecoderFallbackException){return "source_invalid";}
         catch(IOException){return "busy_or_io_error";}
         catch{return "storage_error";}
    }
    // Conservative recovery only for an incomplete final line on the same UTC day.
    // Never infer a lost event's content or overwrite a corrupt complete row.
    // Persist a loss marker BEFORE truncating. This is not a power-failure atomic transaction.
    public static string RecoverTornTail(string root,DateTime day){
        if(!IsDay(day))return "invalid_day";
        try{
            if(!SafeRoot(root))return "root_rejected";
            string path=PathFor(root,Slot(day));
            if(!File.Exists(path))return "not_found";
            if((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)return "reparse_rejected";
            using(var f=File.Open(path,FileMode.Open,FileAccess.ReadWrite,FileShare.None)){
                if(f.Length<=0||f.Length>MaxBytes)return "not_recoverable";
                var bytes=new byte[(int)f.Length];int read=0;
                while(read<bytes.Length){int n=f.Read(bytes,read,bytes.Length-read);if(n==0)return "not_recoverable";read+=n;}
                if(bytes[bytes.Length-1]==10)return "not_torn_tail";
                int last=Array.LastIndexOf(bytes,(byte)10);
                if(last<0||bytes.Length-last-1>256)return "not_recoverable";
                // Validate the entire intact prefix; decode only the prefix, not discarded bytes.
                string prefix=Ascii.GetString(bytes,0,last+1);
                string[] lines=prefix.Split('\n');
                string expected=day.ToString("yyyyMMdd",Inv);
                if(lines.Length<3||lines.Length>MaxRows+2||
                   (lines[0]!="C545D_META_V1|"+expected&&lines[0]!="C545D_META_R1|"+expected))return "not_recoverable";
                for(int i=1;i<lines.Length-1;i++){
                    var row=Decode(lines[i]);
                    if(row.Utc.Date!=day.Date)return "not_recoverable";
                }
                // Same-size header marker, preserves every complete data row verbatim.
                f.Position=0;byte[] marker=Ascii.GetBytes("C545D_META_R1|");
                f.Write(marker,0,marker.Length);f.Flush(true);
                f.SetLength(last+1);f.Flush(true);
                return "recovered_loss_possible";
            }
        }catch(InvalidDataException){return "not_recoverable";}
         catch(FormatException){return "not_recoverable";}
         catch(OverflowException){return "not_recoverable";}
         catch(DecoderFallbackException){return "not_recoverable";}
         catch(IOException){return "busy_or_io_error";}
         catch{return "storage_error";}
    }
    // At most one recovery attempt and one additional append. Never retry busy/IO.
    // Failed full-prefix validation leaves the original slot untouched.
    public static string AppendRecovering(string root,Row row){
        string first=Append(root,row);
        if(first!="source_invalid")return first;
        string recovery=RecoverTornTail(root,row.Utc.Date);
        if(recovery=="recovered_loss_possible"){
            string again=Append(root,row);
            return again=="saved"?"saved_after_recovery":"recovered_append_"+again;
        }
        if(recovery=="not_recoverable"||recovery=="not_torn_tail")return "corrupt_slot_preserved";
        return "recovery_"+recovery;
    }
    public static Snapshot ReadWindow(string root,DateTime begin,DateTime end){
        var result=new Snapshot();
        if(!IsDay(begin)||!IsDay(end)||end<=begin||(end-begin).TotalDays>31){result.Status="window_invalid";return result;}
        try{
            if(!SafeRoot(root)){result.Status="root_rejected";return result;}
            for(int i=0;i<Days;i++){
                string path=PathFor(root,i);if(!File.Exists(path))continue;
                try{
                    if((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0){result.InvalidSlots++;continue;}
                    using(var f=File.Open(path,FileMode.Open,FileAccess.Read,FileShare.Read)){
                        bool recovered;
                        var rows=Read(f,i,out recovered);
                        if(recovered&&rows[0].Utc.Date>=begin.Date&&rows[0].Utc.Date<=end.Date)result.RecoveredSlots++;
                        if(rows.Count==MaxRows&&rows[0].Utc.Date>=begin.Date&&rows[0].Utc.Date<=end.Date)result.SaturatedSlots++;
                        foreach(var row in rows)if(row.Utc>=begin&&row.Utc<end)result.Rows.Add(row);
                    }
                }catch(IOException){result.BusySlots++;}
                 catch{result.InvalidSlots++;}
            }
            result.Rows.Sort((a,b)=>a.Utc.CompareTo(b.Utc));
            // Even all readable slots are not proof all renames published.
            if(result.InvalidSlots>0||result.BusySlots>0||result.SaturatedSlots>0||result.RecoveredSlots>0)result.Status="partial_or_unavailable";
            else if(result.Rows.Count==0)result.Status="no_events_coverage_unverified";
            return result;
        }catch{result.Status="storage_error";result.Rows.Clear();return result;}
    }
}
