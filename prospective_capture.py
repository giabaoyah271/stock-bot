"""Generate a private, timestamped A4 research snapshot; never backfill."""
import hashlib
import io
import json
import zipfile
from pathlib import Path
import pandas as pd
from portfolio_core import Policy,SECTORS,prepare_signals,simulate_portfolio
from entry_filter_core import BY_FILTER,reject_reason

MANIFEST=Path(__file__).resolve().parent/"prospective"/"candidate_a4.json"

def capture_snapshot(histories,now=None):
    config=json.loads(MANIFEST.read_text(encoding="utf-8"))
    t=pd.Timestamp.now(tz="Asia/Ho_Chi_Minh") if now is None else pd.Timestamp(now)
    t=t.tz_localize("Asia/Ho_Chi_Minh") if t.tzinfo is None else t.tz_convert("Asia/Ho_Chi_Minh")
    day=t.date().isoformat()
    if day<=config["frozen_on_vietnam_date"] or (t.hour,t.minute)<(15,15):
        raise ValueError("Chỉ ghi nhận sau ngày khóa và sau 15:15 giờ VN")
    if set(histories)!=set(config["symbols"]):
        raise ValueError("Cần đủ đúng 12 mã")
    signals=prepare_signals(histories,"S0P0")
    last=next(iter(signals.values())).index[-1]
    if last.date().isoformat()!=day:
        raise ValueError("Phiên cuối không phải hôm nay; không ghi bù")
    p=Policy()
    summary,curve,ledger,orders,_=simulate_portfolio(signals,"S0P0","R1",p,entry_gate=lambda s,r:reject_reason(r,BY_FILTER["A4"]))
    holdings={}
    if not orders.empty:
        for _,o in orders.iterrows():
            if o["Lệnh"]=="Mua": holdings[o["Mã"]]=int(o["Số CP"])
            elif o["Lệnh"]=="Bán": holdings.pop(o["Mã"])
    pending=[]
    raw=[]
    for s,d in sorted(signals.items()):
        raw.append(d[["open","high","low","close","volume"]].rename_axis("Ngày").reset_index().assign(Mã=s))
        prev,cur=d.iloc[-2],d.iloc[-1]
        action="Không có tín hiệu mới"
        reason=""
        if prev["Trend"]==1 and cur["Trend"]==-1 and s in holdings: action="Dự kiến bán Open kế tiếp"
        elif prev["Trend"]==-1 and cur["Trend"]==1 and s not in holdings:
            reason=reject_reason(cur,BY_FILTER["A4"])
            action="Loại A4" if reason else "Ứng viên mua; chờ sizing Open"
        pending.append({"Mã":s,"Ngày":last,"CP mô phỏng cuối":holdings.get(s,0),"Close":cur["close"],
                        "Buy_Pct":cur["Buy_Pct"],"Trend":cur["Trend"],"Tín hiệu mới":action,"Lý do":reason})
    if len(holdings)!=summary["Vị thế cuối"]:
        raise ValueError("Vị thế không khớp")
    members={"ohlcv.csv":pd.concat(raw,ignore_index=True),"equity.csv":curve.reset_index(),
             "trades.csv":ledger,"orders.csv":orders,"pending.csv":pd.DataFrame(pending),
             "summary.csv":pd.DataFrame([summary])}
    payload={k:f.to_csv(index=False).encode("utf-8-sig") for k,f in members.items()}
    manifest={"recorded_at_vn":t.isoformat(),"as_of_session_vn":day,"source":"TCBS",
              "candidate":config,"sha256":{k:hashlib.sha256(v).hexdigest() for k,v in payload.items()},
              "warning":"Recomputed historical simulation, not independently verified contemporaneous fills. Keep originals private; never backfill or overwrite. Compare raw histories across snapshots for revisions."}
    payload["manifest.json"]=json.dumps(manifest,ensure_ascii=False,indent=2).encode("utf-8")
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for k,v in payload.items(): z.writestr(k,v)
    result=buf.getvalue()
    return result,hashlib.sha256(result).hexdigest(),manifest,pd.DataFrame(pending)
