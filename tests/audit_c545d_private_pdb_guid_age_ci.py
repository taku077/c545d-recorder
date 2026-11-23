#!/usr/bin/env python3
"""PE CodeView RSDS ↔ native MSVC MSF-7 PDB GUID+age verifier.

Strict evidence preflight for a disposable Windows 2022 GLib build.
No PDB bytes/paths/GUIDs, module names, registry data or trace stacks leave CI.
It does NOT by itself prove a symbol resolves to a GIO AppInfo function:
actual ETLX CallStack+Method must still pass an independent gate.

No remote downloads or forced DLL loads. Never replace installed recorder DLLs.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import struct
import sys

MZ = b"MZ"
MAGIC = b"Microsoft C/C++ MSF 7.00\r\n\x1aDS\x00\x00\x00"
MAX_DLL = 80 * 1024 * 1024
MAX_PDB = 128 * 1024 * 1024

def get_u32(blob: bytes, offset: int)->int:
    if offset < 0 or offset+4 > len(blob):raise ValueError("out_of_range_integer")
    return struct.unpack_from("<I",blob,offset)[0]

def get_u16(blob: bytes, offset: int)->int:
    if offset < 0 or offset+2 > len(blob):raise ValueError("out_of_range_integer")
    return struct.unpack_from("<H",blob,offset)[0]

def pe_codeview(blob:bytes)->tuple[bytes,int,str]:
    if len(blob)<512 or len(blob)>MAX_DLL or blob[:2]!=MZ:
        raise ValueError("invalid_or_oversized_PE")
    pe=get_u32(blob,0x3c)
    if pe<64 or pe+24>len(blob) or blob[pe:pe+4]!=b"PE\x00\x00":
        raise ValueError("missing_PE_signature")
    nsect=get_u16(blob,pe+6)
    optsize=get_u16(blob,pe+20)
    if nsect<1 or nsect>96 or optsize<96 or pe+24+optsize>len(blob):
        raise ValueError("invalid_PE_sections")
    opt=pe+24
    magic=get_u16(blob,opt)
    if magic==0x20b: dirs=opt+112
    elif magic==0x10b: dirs=opt+96
    else:raise ValueError("unsupported_PE_optional_header")
    if dirs+7*8>opt+optsize:raise ValueError("no_debug_directory")
    debug_rva=get_u32(blob,dirs+6*8)
    debug_len=get_u32(blob,dirs+6*8+4)
    if debug_rva==0 or debug_len==0 or debug_len%28 or debug_len>896:
        raise ValueError("missing_or_ambiguous_CodeView_debug_directory")
    sections=[]
    sec=opt+optsize
    for i in range(nsect):
        off=sec+i*40
        if off+40>len(blob):raise ValueError("truncated_PE_sections")
        virtual_size=get_u32(blob,off+8)
        virtual_addr=get_u32(blob,off+12)
        raw_size=get_u32(blob,off+16)
        raw_ptr=get_u32(blob,off+20)
        if raw_ptr+raw_size>len(blob):raise ValueError("invalid_PE_section_extent")
        sections.append((virtual_addr,max(virtual_size,raw_size),raw_ptr,raw_size))
    debug_off=None
    for start,size,ptr,rawsize in sections:
        if start<=debug_rva and debug_rva+debug_len<=start+min(size,rawsize):
            debug_off=ptr+(debug_rva-start)
            break
    if debug_off is None:raise ValueError("unmapped_debug_directory")
    rsds=[]
    for off in range(debug_off,debug_off+debug_len,28):
        typ=get_u32(blob,off+12)
        count=get_u32(blob,off+16)
        ptr=get_u32(blob,off+24)
        if typ!=2:continue
        if count<25 or count>4096 or ptr+count>len(blob):
            raise ValueError("CodeView_record_truncated")
        cv=blob[ptr:ptr+count]
        if cv[:4]!=b"RSDS":raise ValueError("unsupported_CodeView_type")
        path_bytes=cv[24:].split(b"\0",1)[0]
        if not path_bytes or len(path_bytes)>512:
            raise ValueError("missing_PE_PDB_basename")
        # Only compare expected basename; never output private build path.
        name=path_bytes.replace(b"\\",b"/").split(b"/")[-1].decode("ascii","strict").lower()
        if not name.endswith(".pdb"):
            raise ValueError("invalid_PE_PDB_suffix")
        rsds.append((cv[4:20],get_u32(cv,20),name))
    if len(rsds)!=1:
        raise ValueError("CodeView_record_not_unique")
    return rsds[0]

def pdb_msf_info(blob:bytes)->tuple[bytes,int]:
    if len(blob)<512 or len(blob)>MAX_PDB or not blob.startswith(MAGIC):
        raise ValueError("unsupported_MSVC_PDB_format")
    page_size=get_u32(blob,32)
    page_count=get_u32(blob,40)
    dir_size=get_u32(blob,44)
    map_page=get_u32(blob,52)
    if page_size<512 or page_size>65536 or page_size&(page_size-1):
        raise ValueError("unsupported_PDB_page_size")
    if page_count<2 or page_count*page_size>len(blob) or dir_size<20 or dir_size>16*1024*1024:
        raise ValueError("PDB_directory_out_of_bounds")
    dir_pages=(dir_size+page_size-1)//page_size
    if dir_pages>page_size//4 or map_page>=page_count:
        raise ValueError("PDB_directory_page_table_unbounded")
    mapoff=map_page*page_size
    if mapoff+dir_pages*4>len(blob):
        raise ValueError("PDB_directory_map_truncated")
    data=bytearray()
    for j in range(dir_pages):
        page=get_u32(blob,mapoff+j*4)
        if page>=page_count:raise ValueError("PDB_directory_invalid_page")
        data.extend(blob[page*page_size:(page+1)*page_size])
    directory=bytes(data[:dir_size])
    streams=get_u32(directory,0)
    if streams<2 or streams>100_000 or 4+streams*4>len(directory):
        raise ValueError("PDB_stream_count_invalid")
    sizes=[get_u32(directory,4+4*i) for i in range(streams)]
    pos=4+4*streams
    info_pages=None
    info_len=sizes[1]
    if info_len<28 or info_len>8*1024*1024:
        raise ValueError("PDB_info_stream_invalid")
    for index,stream_size in enumerate(sizes):
        n=0 if stream_size==0xFFFFFFFF else (stream_size+page_size-1)//page_size
        if pos+4*n>len(directory):raise ValueError("PDB_stream_pages_truncated")
        if index==1:
            info_pages=[get_u32(directory,pos+4*i) for i in range(n)]
        pos+=n*4
    if info_pages is None:raise ValueError("PDB_info_stream_missing")
    info=bytearray()
    for page in info_pages:
        if page>=page_count:raise ValueError("PDB_info_page_invalid")
        info.extend(blob[page*page_size:(page+1)*page_size])
    info=info[:info_len]
    age=get_u32(info,8)
    guid=bytes(info[12:28])
    if age<1 or age>1_000_000 or guid==b"\0"*16:
        raise ValueError("PDB_info_guid_or_age_invalid")
    return guid,age

def verify(dll:bytes,pdb:bytes,expected_basename:str)->str:
    cv_guid,cv_age,cv_path=pe_codeview(dll)
    pdb_guid,pdb_age=pdb_msf_info(pdb)
    if cv_path!=expected_basename.lower():
        raise ValueError("unexpected_PDB_basename")
    if (cv_guid,cv_age)!=(pdb_guid,pdb_age):
        raise ValueError("DLL_PDB_GUID_age_mismatch")
    return (
        "C545D_GIO_PE_PDB_IDENTITY_PASS,pe_codeview_RSDS=1,"
        "msvc_PDB_stream1_guid_age=1,exact_guid_age_matched=1,"
        "private_symbol_source=1,actual_GIO_function_resolved=0,"
        "raw_pdb_path_or_guid_output=0,real_recorder_untouched=1,"
        "release_HOLD=1"
    )

def synthetic_pair(*,bad_guid:bool=False)->tuple[bytes,bytes]:
    page=512
    guid=bytes(range(1,17))
    age=3
    pdb=bytearray(page*8)
    pdb[:len(MAGIC)]=MAGIC
    struct.pack_into("<IIIIII",pdb,32,page,0,8,48,0,2)
    struct.pack_into("<I",pdb,2*page,1) # directory page #1
    dir=bytearray(page)
    struct.pack_into("<I",dir,0,2)      # streams 0 and 1
    struct.pack_into("<II",dir,4,0,28)
    struct.pack_into("<I",dir,12,3)    # info on page 3
    pdb[page:2*page]=dir
    info=bytearray(page)
    struct.pack_into("<III",info,0,20000404,1234,age)
    info[12:28]=b"\x99"*16 if bad_guid else guid
    pdb[3*page:4*page]=info
    dll=bytearray(2048)
    dll[:2]=b"MZ"
    struct.pack_into("<I",dll,0x3c,0x80)
    dll[0x80:0x84]=b"PE\0\0"
    struct.pack_into("<HHIIIHH",dll,0x84,0x8664,1,0,0,0,240,0x2022)
    opt=0x98
    struct.pack_into("<H",dll,opt,0x20b)
    # section .rdata rva 0x2000, raw data at 0x200
    debug_rva=0x2000
    struct.pack_into("<II",dll,opt+112+6*8,debug_rva,28)
    sec=opt+240
    dll[sec:sec+8]=b".rdata\0\0"
    struct.pack_into("<IIII",dll,sec+8,0x400,0x2000,0x400,0x200)
    cv=b"RSDS"+guid+struct.pack("<I",age)+b"gio-2.0-0.pdb\0"
    struct.pack_into("<IIHHIIII",dll,0x200,0,0,0,0,2,len(cv),0x3000,0x250)
    dll[0x250:0x250+len(cv)]=cv
    return bytes(dll),bytes(pdb)

def selftest()->None:
    dll,pdb=synthetic_pair()
    assert "exact_guid_age_matched=1" in verify(dll,pdb,"gio-2.0-0.pdb")
    mutations=[
        (b"\0"*len(dll),pdb,"gio-2.0-0.pdb"),
        (dll[:-1900],pdb,"gio-2.0-0.pdb"),
        (dll,pdb[:-3800],"gio-2.0-0.pdb"),
        (dll,pdb,"glib-2.0-0.pdb"),
        (dll,synthetic_pair(bad_guid=True)[1],"gio-2.0-0.pdb"),
        (dll,pdb.replace(MAGIC,b"X"*len(MAGIC),1),"gio-2.0-0.pdb"),
    ]
    for i,inputs in enumerate(mutations):
        try:verify(*inputs)
        except (ValueError,UnicodeError):continue
        raise AssertionError(f"invalid_private_PDB_provenance_accepted:{i}")
    print("C545D_GIO_PE_PDB_SELFTEST_PASS,positive=1,negative=6,"
          "pdb_GUID_age_mismatch_rejected=1,wrong_basename_rejected=1,"
          "no_real_GIO_symbol_claim=1,host_untouched=1")

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--dll",type=Path)
    group=p.add_mutually_exclusive_group()
    group.add_argument("--pdb",type=Path)
    group.add_argument("--pdb-root",type=Path)
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.dll is None or (a.pdb is None and a.pdb_root is None):
        p.error("--dll and (--pdb or --pdb-root) required")
    if os.environ.get("GITHUB_ACTIONS")!="true" or os.environ.get("RUNNER_OS")!="Windows":
        raise SystemExit("C545D_GIO_PE_PDB_GAP,reason=NOT_DISPOSABLE_WINDOWS_CI,release_HOLD=1")
    temp=os.environ.get("RUNNER_TEMP")
    if not temp:
        raise SystemExit("C545D_GIO_PE_PDB_GAP,reason=CI_TEMP_MISSING,release_HOLD=1")
    root=Path(temp).resolve()
    try:
        dll=a.dll.resolve(strict=True)
        if root not in dll.parents or dll.stat().st_size>MAX_DLL:
            raise ValueError("nonprivate_DLL")
        dllbytes=dll.read_bytes()
        expected=pe_codeview(dllbytes)[2]
        if a.pdb_root is not None:
            base=a.pdb_root.resolve(strict=True)
            if root not in base.parents:
                raise ValueError("nonprivate_PDB_search_path")
            # GitHub runner-local build only, not an external symbol server.
            candidates=list(base.rglob("*.pdb"))
            if len(candidates)>1000:
                raise ValueError("unbounded_PDB_inventory")
            possible=[c for c in candidates if c.name.lower()==expected]
            if len(possible)!=1:
                raise ValueError("PDB_not_unique_or_missing")
            pdb=possible[0].resolve(strict=True)
        else:
            pdb=a.pdb.resolve(strict=True)
        if root not in pdb.parents or pdb.stat().st_size>MAX_PDB:
            raise ValueError("nonprivate_PDB")
        print(verify(dllbytes,pdb.read_bytes(),expected))
    except (ValueError,OSError) as ex:
        # Never show the filename or even exception text on public CI logs.
        print("C545D_GIO_PE_PDB_GAP,reason=SOURCE_FILE_OR_GUID_AGE_UNVERIFIED,"
              "real_GIO_function_resolved=0,release_HOLD=1")
        raise SystemExit(2) from None

if __name__=="__main__":
    main()
