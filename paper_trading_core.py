"""PT03-08: incremental research-only paper account. No broker orders or server persistence."""
import hashlib,json,math
from dataclasses import asdict
import numpy as np
import pandas as pd
from portfolio_core import Policy,size_order,_reference
from robustness_core import stats_equity
from universe_u5 import U5,U5_VERSION
from full_universe_core import UNAVAILABLE,SHA_B
from universe_prepare_core import SECTORS
from signal_engine_core import local_now,STATES,END

VERSION="PT03-08-v1"
POLICY=Policy()
COHORT=tuple(s for s in U5 if s not in UNAVAILABLE)
assert len(COHORT)==115
MAX_BYTES=32*1024*1024
MAX_SESSIONS=500
def canonical(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
def digest(x):
    return hashlib.sha256(canonical(x)).hexdigest()
def config():
    return {"version":VERSION,"candidate":"U5-A0-RS60-P5-R050","strategy":"S0P0","rank":"RS60, Buy Score, ticker",
            "watchlist":U5_VERSION,"symbols":list(COHORT),"sectors":{s:SECTORS[s] for s in COHORT},
            "reference_sha":SHA_B,"historical_end":str(END.date()),"policy":asdict(POLICY),
            "execution":"Previous completed close signal -> next completed session's reported Open; simulated after close",
            "compliance":"Unverified; research only; no real orders"}
def new_account(mode="PAPER",now=None):
    if mode not in ("PAPER","TEST"): raise ValueError("Chế độ sai")
    t=local_now(now)
    if mode=="PAPER" and t.date()<=END.date(): raise ValueError("Ngày khởi tạo trước mốc nghiên cứu")
    head={"mode":mode,"frozen_at":t.isoformat(),"config":config()}
    return {"header":head,"header_sha":digest(head),"events":[]}
def timestamp(value):
    t=pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None: raise ValueError("Thiếu múi giờ")
    return local_now(t)
def day(value):
    d=pd.Timestamp(value)
    if pd.isna(d) or d.tzinfo is not None or d!=d.normalize() or str(d.date())!=value: raise ValueError("Ngày phiên không hợp lệ")
    return d
def hexsha(v):
    return isinstance(v,str) and len(v)==64 and all(c in "0123456789abcdef" for c in v)
def number(v,positive=False):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or (positive and v<=0): raise ValueError("Giá/số liệu không hợp lệ")
    return float(v)

def risk_preview(equity,cash,price,close,atr,sector_used,heat,positions,already_held=False):
    """All currency arguments in VND; use original KT06 R1 sizing."""
    vals=[equity,cash,price,close,atr,sector_used,heat]
    if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in vals) or min(equity,price,close)<=0 or min(cash,atr,sector_used,heat)<0 or not isinstance(positions,int) or not 0<=positions<=POLICY.max_positions:
        raise ValueError("Thông số quản trị vốn không hợp lệ")
    ref=_reference("S0P0",price,{"close":close,"ATR":atr})
    if already_held or positions>=POLICY.max_positions:
        qty,unit,reason=0,0.,"Đã có vị thế" if already_held else "Giới hạn vị thế"
    else: qty,unit,reason=size_order(equity,cash,price,ref,sector_used,heat,POLICY,"R1")
    cost=qty*price*POLICY.costs.buy_mult
    return {"qty":qty,"reference":ref,"unit_risk":unit,"cost":cost,"risk":qty*unit,"reason":reason,
            "risk_budget":equity*POLICY.risk,"stock_cap":equity*POLICY.stock_cap}

def snapshot_from_report(report,now=None):
    """Only fresh, complete in-session PT02 LIVE scan; no imported historical ZIP."""
    t=local_now(now);identity=report.get("identity",())
    if len(identity)!=4 or identity[3]!="LIVE" or identity[2]!=SHA_B: raise ValueError("Cần quét PT02 LIVE; không dùng TEST")
    session=identity[0]
    if session!=str(t.date()) or (t.hour,t.minute)<(15,15): raise ValueError("Chỉ ghi phiên hôm nay sau 15:15 giờ VN; không ghi bù")
    rows=report["rows"]
    if set(rows)!=set(U5): raise ValueError("Cần quét đủ 120 mã trong cùng phiên")
    observed=timestamp(report["updated"])
    if observed.date()!=t.date() or observed>t: raise ValueError("Báo cáo không được ghi nhận hôm nay")
    data={}
    for s in COHORT:
        r=rows[s]
        if r.get("Kỹ thuật")!="Khớp mẫu KT18" or r.get("Phiên cuối")!=session or r.get("Chế độ")!="QUÉT PHIÊN MỚI":
            raise ValueError(s+": thiếu dữ liệu khớp mẫu; dừng toàn bộ phiên")
        captured=timestamp(r["Ghi nhận (VN)"])
        if captured.date()!=t.date() or captured>observed or (captured.hour,captured.minute)<(15,15):
            raise ValueError(s+": thời điểm quét không hợp lệ")
        data[s]={"open":float(r["Open (nghìn VND)"])*1000,"close":float(r["Close (nghìn VND)"])*1000,
                 "atr":float(r["ATR (nghìn VND)"])*1000,"prev":int(r["Trend trước"]),"trend":int(r["Trend"]),
                 "rs":float(r["RS60 (đpt)"]),"score":float(r["Buy Score (%)"]),
                 "sha":r["SHA lịch sử"],"previous_sha":r["SHA lịch sử trước phiên"]}
    return {"session":session,"previous_session":report["previous_session"],"index_sha":identity[1],
            "previous_index_sha":report["previous_index_sha"],"observed_at":observed.isoformat(),"recorded_at":t.isoformat(),
            "source":"PT02 LIVE TCBS","rows":data}

def validate_event(e,header,previous):
    if set(e)!={"session","previous_session","index_sha","previous_index_sha","observed_at","recorded_at","source","rows"}:
        raise ValueError("Schema phiên không hợp lệ")
    dt=day(e["session"]);prev=day(e["previous_session"]);obs=timestamp(e["observed_at"]);rec=timestamp(e["recorded_at"]);freeze=timestamp(header["frozen_at"])
    if prev>=dt or dt.date()<=freeze.date() or obs.date()!=dt.date() or rec.date()!=dt.date() or obs>rec or (obs.hour,obs.minute)<(15,15):
        raise ValueError("Phiên phải ghi sau ngày khóa, cùng ngày sau 15:15, không ghi bù")
    if header["mode"]=="PAPER" and (dt<=END or e["source"]!="PT02 LIVE TCBS"): raise ValueError("Không dùng dữ liệu kiểm thử/hồi cứu")
    if header["mode"]=="TEST" and e["source"]!="SYNTHETIC TEST": raise ValueError("Sai nguồn kiểm thử")
    if not hexsha(e["index_sha"]) or not hexsha(e["previous_index_sha"]) or set(e["rows"])!=set(COHORT):
        raise ValueError("Thiếu 115 mã hoặc dấu vân tay VN-Index")
    if previous:
        if e["previous_session"]!=previous["session"] or e["previous_index_sha"]!=previous["index_sha"]:
            raise ValueError("Thiếu phiên, trùng phiên hoặc VN-Index thay đổi; không tự ghi bù")
        if rec<=timestamp(previous["recorded_at"]): raise ValueError("Thời điểm nhật ký không tăng")
    for s,r in e["rows"].items():
        if set(r)!={"open","close","atr","prev","trend","rs","score","sha","previous_sha"}: raise ValueError(s+": schema sai")
        for k in ("open","close"): number(r[k],True)
        if number(r["atr"])<0 or not 0<=number(r["score"])<=100: raise ValueError(s+": ATR/điểm sai")
        number(r["rs"])
        if type(r["prev"]) is not int or type(r["trend"]) is not int or (r["prev"],r["trend"]) not in STATES or not hexsha(r["sha"]) or not hexsha(r["previous_sha"]):
            raise ValueError(s+": Trend hoặc SHA sai")
        if previous and (r["previous_sha"]!=previous["rows"][s]["sha"] or r["prev"]!=previous["rows"][s]["trend"]):
            raise ValueError(s+": lịch sử/tín hiệu phiên trước thay đổi; dừng phiên")

def replay(account):
    """Validate every input and hash chain; recompute outputs from cash and event rows."""
    if set(account)!={"header","header_sha","events"}: raise ValueError("Schema tài khoản không hợp lệ")
    h=account["header"]
    if set(h)!={"mode","frozen_at","config"} or h["mode"] not in ("PAPER","TEST") or h["config"]!=config() or digest(h)!=account["header_sha"]:
        raise ValueError("Cấu hình/hash khóa không khớp")
    freeze=timestamp(h["frozen_at"])
    if h["mode"]=="PAPER" and freeze.date()<=END.date(): raise ValueError("Ngày khóa không hợp lệ")
    events=account["events"]
    if not isinstance(events,list) or len(events)>MAX_SESSIONS: raise ValueError("Nhật ký quá lớn")
    p=POLICY;cash=p.capital;positions={};orders=[];trades=[];daily=[];prior=None;chain=account["header_sha"];peak=cash
    for item in events:
        if set(item)!={"input","previous_hash","hash"} or item["previous_hash"]!=chain or digest({"input":item["input"],"previous_hash":chain})!=item["hash"]:
            raise ValueError("Chuỗi hash nhật ký không khớp")
        e=item["input"];validate_event(e,h,prior);chain=item["hash"];rows=e["rows"];date=e["session"]
        # No signals before first recorded close. On subsequent dates use prior close ONLY.
        if prior:
            prev=prior["rows"]
            for s in sorted(list(positions)):
                if (prev[s]["prev"],prev[s]["trend"])==(1,-1):
                    pos=positions.pop(s);price=rows[s]["open"];proceeds=pos["qty"]*price*p.costs.sell_mult
                    cash+=proceeds;pnl=proceeds-pos["cost"]
                    orders.append({"Ngày":date,"Mã":s,"Lệnh":"Bán mô phỏng","CP":pos["qty"],"Open (VND)":price,"Lý do":"","Giá trị (VND)":proceeds})
                    trades.append({"Mã":s,"Ngày mua":pos["date"],"Ngày bán":date,"Ngày tín hiệu bán":prior["session"],"CP":pos["qty"],"Vốn mua (VND)":pos["cost"],"Thu bán (VND)":proceeds,"P&L (VND)":pnl,"LN (%)":100*pnl/pos["cost"],"Rủi ro ban đầu":pos["risk"],"Lỗ vượt ngân sách":pnl<-pos["risk"]})
            candidates=sorted((s for s,r in prev.items() if (r["prev"],r["trend"])==(-1,1) and s not in positions),key=lambda s:(-prev[s]["rs"],-prev[s]["score"],s))
            for s in candidates:
                r=prev[s];price=rows[s]["open"]
                equity=cash+sum(pos["qty"]*rows[x]["open"] for x,pos in positions.items())
                sector=sum(pos["qty"]*rows[x]["open"] for x,pos in positions.items() if SECTORS[x]==SECTORS[s])
                heat=sum(pos["risk"] for pos in positions.values())
                plan=risk_preview(equity,cash,price,r["close"],r["atr"],sector,heat,len(positions))
                qty=plan["qty"]
                orders.append({"Ngày":date,"Mã":s,"Lệnh":"Mua mô phỏng" if qty else "Bỏ mua","CP":qty,"Open (VND)":price,
                    "Lý do":plan["reason"],"Giá trị (VND)":plan["cost"],"Stop tham chiếu":plan["reference"],"Rủi ro (VND)":plan["risk"],
                    "Equity trước mua":equity,"Ngày tín hiệu":prior["session"]})
                if qty:
                    if plan["cost"]>cash+1e-6 or plan["risk"]>equity*p.risk+1e-6 or plan["cost"]>equity*p.stock_cap+1e-6 or sector+plan["cost"]>equity*p.sector_cap+1e-6 or heat+plan["risk"]>equity*p.heat_cap+1e-6: raise ValueError("Vi phạm giới hạn lúc mua")
                    cash-=plan["cost"];positions[s]={"qty":qty,"cost":plan["cost"],"risk":plan["risk"],"date":date,"signal":prior["session"],"reference":plan["reference"]}
        value=sum(pos["qty"]*rows[s]["close"] for s,pos in positions.items());equity=cash+value
        if cash<-1e-6 or equity<=0 or len(positions)>p.max_positions: raise ValueError("Vi phạm tiền mặt/vị thế")
        peak=max(peak,equity);heat=sum(pos["risk"] for pos in positions.values())
        realized=sum(x["P&L (VND)"] for x in trades);unrealized=value-sum(pos["cost"] for pos in positions.values())
        if not math.isclose(equity-p.capital,realized+unrealized,rel_tol=0,abs_tol=.01): raise ValueError("P&L không khớp")
        daily.append({"Ngày":date,"Equity":equity,"Tiền mặt":cash,"Giá trị vị thế":value,"Drawdown (%)":100*(equity/peak-1),"Số vị thế":len(positions),"Exposure (%)":100*value/equity,"Heat (%)":100*heat/equity,"P&L đã đóng":realized,"P&L mở":unrealized})
        prior=e
    holdings=[]
    if prior:
        for s,pos in sorted(positions.items()):
            val=pos["qty"]*prior["rows"][s]["close"]
            holdings.append({"Mã":s,"Ngành":SECTORS[s],"CP":pos["qty"],"Ngày mua":pos["date"],"Vốn mua":pos["cost"],"Giá trị Close":val,"P&L mở":val-pos["cost"],"Rủi ro ban đầu":pos["risk"]})
    pending=[]
    if prior:
        for s,r in sorted(prior["rows"].items(),key=lambda x:(-x[1]["rs"],-x[1]["score"],x[0])):
            action="Mua mới dự kiến" if (r["prev"],r["trend"])==(-1,1) and s not in positions else "Thoát dự kiến" if (r["prev"],r["trend"])==(1,-1) and s in positions else None
            if action: pending.append({"Mã":s,"Tín hiệu":action,"Ngày tín hiệu":prior["session"],"RS60":r["rs"],"Buy Score":r["score"],"Close":r["close"],"ATR":r["atr"]})
    return {"cash":cash,"equity":daily[-1]["Equity"] if daily else cash,"holdings":holdings,"pending":pending,"orders":orders,"trades":trades,"daily":daily,"last_hash":chain}

def append_session(account,event):
    prior=replay(account)
    item={"input":event,"previous_hash":prior["last_hash"]}
    item["hash"]=digest(item)
    nxt={**account,"events":[*account["events"],item]}
    replay(nxt)
    return nxt

def export_account(account):
    replay(account)
    return canonical(account)
def import_account(data,mode="PAPER",now=None):
    if not data or len(data)>MAX_BYTES: raise ValueError("File nhật ký quá lớn hoặc rỗng")
    a=json.loads(data)
    if a["header"]["mode"]!=mode: raise ValueError("Không trộn tài khoản TEST và PAPER")
    if timestamp(a["header"]["frozen_at"])>local_now(now) or any(timestamp(x["input"]["recorded_at"])>local_now(now) for x in a["events"]):
        raise ValueError("Nhật ký chứa thời điểm tương lai")
    replay(a)
    return a

def performance(result):
    d=result["daily"];tr=result["trades"];pnl=[x["P&L (VND)"] for x in tr];loss=-sum(x for x in pnl if x<0);wins=sum(x for x in pnl if x>0)
    m=stats_equity([POLICY.capital]+[x["Equity"] for x in d])
    years=(day(d[-1]["Ngày"])-day(d[0]["Ngày"])).days/365.25 if len(d)>1 else 0
    cagr=100*((result["equity"]/POLICY.capital)**(1/years)-1) if years>=1 else None
    return {"Số phiên":len(d),"Lệnh đóng":len(tr),**m,"Profit Factor":wins/loss if loss>0 else None,"Win Rate (%)":100*sum(x>0 for x in pnl)/len(tr) if tr else None,
            "Expectancy (%)":float(np.mean([x["LN (%)"] for x in tr])) if tr else None,"CAGR (%)":cagr,"Calmar":cagr/abs(m["MDD (%)"]) if cagr is not None and m["MDD (%)"]<0 else None}
def readiness(result,mode):
    m=performance(result)
    checks=[("Paper, không phải TEST",mode=="PAPER"),("Ít nhất 60 phiên (sơ bộ)",m["Số phiên"]>=60),("Ít nhất 30 lệnh đóng (sơ bộ)",m["Lệnh đóng"]>=30),
            ("MDD lịch sử ≤10%",m["MDD (%)"]>=-10),("Profit Factor ≥1.5",m["Profit Factor"] is not None and m["Profit Factor"]>=1.5),
            ("Expectancy dương",m["Expectancy (%)"] is not None and m["Expectancy (%)"]>0),("Win Rate ≥55%",m["Win Rate (%)"] is not None and m["Win Rate (%)"]>=55),
            ("Sharpe ≥1",m["Sharpe (rf=0)"] is not None and m["Sharpe (rf=0)"]>=1),("Sortino ≥1.5",m["Sortino (MAR=0)"] is not None and m["Sortino (MAR=0)"]>=1.5),
            ("Calmar ≥1.5 (≥1 năm)",m["Calmar"] is not None and m["Calmar"]>=1.5),("Xác minh pháp lý/Free Float/BCTC độc lập",False),
            ("Khớp lệnh, thanh khoản, giá điều chỉnh/corporate actions đã kiểm chứng",False),("Độ bền ngoài mẫu và Monte Carlo mục tiêu",False)]
    return [{"Tiêu chí":k,"Đạt":bool(v)} for k,v in checks]
