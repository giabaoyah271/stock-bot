"""Safe bounded JSON/gzip codec for scan frames; no pickle, no executable types."""
import gzip
import io
import json
import math
import re
import numpy as np
import pandas as pd
from storage_ds01 import StorageError,MAX_OBJECT,json_bytes

MAX_DECODE=256*1024*1024

def scalar(v):
    if v is pd.NA or v is pd.NaT or v is None: return None
    if isinstance(v,np.generic): v=v.item()
    if isinstance(v,float):
        if math.isnan(v): return None
        if not math.isfinite(v): raise StorageError("Giá trị vô hạn")
    if type(v) in (str,int,float,bool): return v
    raise StorageError("Kiểu dữ liệu không hỗ trợ")

def plain(v):
    if isinstance(v,dict):
        if not all(isinstance(k,str) for k in v): raise StorageError("Key không hợp lệ")
        return {k:plain(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)): return [plain(x) for x in v]
    return scalar(v)

def frame_pack(d):
    if not isinstance(d,pd.DataFrame) or not isinstance(d.index,pd.DatetimeIndex) or d.index.hasnans or not d.index.is_unique or not d.index.is_monotonic_increasing or not d.columns.is_unique:
        raise StorageError("Frame không hợp lệ")
    return {"index":[x.isoformat() for x in d.index],"index_name":d.index.name,"tz":str(d.index.tz) if d.index.tz is not None else None,
            "columns":[{"name":c,"dtype":str(d[c].dtype),"values":[scalar(x) for x in d[c]]} for c in d.columns]}

def frame_unpack(p):
    if not isinstance(p,dict) or set(p)!={"index","index_name","tz","columns"} or len(p["index"])>15000 or len(p["columns"])>100:
        raise StorageError("Schema frame không hợp lệ")
    idx=pd.DatetimeIndex(pd.to_datetime(p["index"],utc=p["tz"] is not None))
    if p["tz"] is not None: idx=idx.tz_convert(p["tz"])
    idx=idx.rename(p["index_name"])
    cols={}
    for c in p["columns"]:
        name,dt,values=c["name"],c["dtype"],c["values"]
        if not isinstance(name,str) or name in cols or not re.fullmatch(r"(float(32|64)|u?int(8|16|32|64)|Int(8|16|32|64)|UInt(8|16|32|64)|bool|boolean|object|string)",dt) or len(values)!=len(idx):
            raise StorageError("Cột frame không hợp lệ")
        cols[name]=pd.Series(values,index=idx,dtype=dt)
    return pd.DataFrame(cols,index=idx)

def compress(value):
    raw=json_bytes(value)
    if len(raw)>MAX_DECODE: raise StorageError("Báo cáo vượt giới hạn giải nén")
    data=gzip.compress(raw,mtime=0)
    if len(data)>MAX_OBJECT: raise StorageError("Báo cáo vượt giới hạn object")
    return data

def decompress(data):
    if len(data)>MAX_OBJECT: raise StorageError("Object quá lớn")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as f: raw=f.read(MAX_DECODE+1)
        if len(raw)>MAX_DECODE: raise StorageError("Báo cáo giải nén quá lớn")
        return json.loads(raw)
    except (OSError,EOFError,UnicodeError,ValueError): raise StorageError("Báo cáo nén không hợp lệ") from None

def validate_report(r):
    from unified_strategy_core import validate_chart
    from signal_engine_core import U5,END
    from full_universe_core import SHA_B
    from paper_trading_core import timestamp,hexsha
    if set(r)!={"identity","rows","charts","updated","previous_session","previous_index_sha"}:
        raise StorageError("Schema báo cáo không hợp lệ")
    ident=r["identity"]
    if len(ident)!=4 or ident[2:]!=(SHA_B,"LIVE") or not hexsha(ident[1]) or not hexsha(r["previous_index_sha"]):
        raise StorageError("Không phải báo cáo LIVE đúng U5-B")
    if pd.Timestamp(ident[0])<=END or not pd.Timestamp(r["previous_session"])<pd.Timestamp(ident[0]):
        raise StorageError("Ngày báo cáo không hợp lệ")
    timestamp(r["updated"])
    if not r["rows"] or not set(r["rows"]).issubset(U5): raise StorageError("Mã báo cáo không hợp lệ")
    verified={s for s,row in r["rows"].items() if row.get("Kỹ thuật")=="Khớp mẫu KT18"}
    if set(r["charts"])!=verified: raise StorageError("Thiếu biểu đồ xác minh")
    for s,row in r["rows"].items():
        if row.get("Mã")!=s: raise StorageError("Mã dòng không khớp")
        if s in verified: validate_chart(s,r["charts"][s],row,ident[0])
    return r

def encode_report(r):
    validate_report(r)
    return compress({"schema":1,"report":plain({k:v for k,v in r.items() if k!="charts"}),"charts":{s:frame_pack(d) for s,d in r["charts"].items()}})

def decode_report(data):
    p=decompress(data)
    if p.get("schema")!=1: raise StorageError("Phiên bản báo cáo không hỗ trợ")
    r=p["report"];r["identity"]=tuple(r["identity"]);r["charts"]={s:frame_unpack(d) for s,d in p["charts"].items()}
    return validate_report(r)

def validate_single(s):
    from unified_strategy_core import validate_chart
    from full_universe_core import SHA_B
    from paper_trading_core import timestamp,hexsha
    if set(s)!={"identity","row","frame","observed_at"} or len(s["identity"])!=4 or s["identity"][2:]!=(SHA_B,"LIVE") or not hexsha(s["identity"][1]):
        raise StorageError("Snapshot riêng không hợp lệ")
    timestamp(s["observed_at"])
    validate_chart(s["row"]["Mã"],s["frame"],s["row"],s["identity"][0])
    return s

def encode_single(s):
    validate_single(s)
    return compress({"schema":1,"single":plain({k:v for k,v in s.items() if k!="frame"}),"frame":frame_pack(s["frame"])})

def decode_single(data):
    p=decompress(data)
    if p.get("schema")!=1: raise StorageError("Phiên bản snapshot không hỗ trợ")
    s=p["single"];s["identity"]=tuple(s["identity"]);s["frame"]=frame_unpack(p["frame"])
    return validate_single(s)
