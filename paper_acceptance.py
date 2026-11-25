"""One-click synthetic end-to-end acceptance. No TCBS or historical ZIP required."""
import copy
import json
from datetime import timedelta
import pandas as pd
from paper_trading_core import (
    COHORT,POLICY,new_account,append_session,replay,export_account,import_account,
    risk_preview,performance,readiness,digest,snapshot_from_report
)
from portfolio_core import size_order

def event(date,previous=None,changes=None):
    """Synthetic prices/signals, NEVER a market observation."""
    d=pd.Timestamp(date)
    old=previous["rows"] if previous else {}
    rows={}
    for s in COHORT:
        prev=old.get(s,{}).get("trend",-1)
        r={"open":25000.,"close":25000.,"atr":750.,"prev":prev,"trend":prev,"rs":0.,"score":60.,
           "previous_sha":old.get(s,{}).get("sha",digest([s,"synthetic initial"]))}
        r.update((changes or {}).get(s,{}))
        r["sha"]=digest([date,s,r])
        rows[s]=r
    return {"session":date,"previous_session":previous["session"] if previous else str((d-pd.Timedelta(days=1)).date()),
            "index_sha":digest(["synthetic index",date]),"previous_index_sha":previous["index_sha"] if previous else digest("synthetic index initial"),
            "observed_at":date+"T15:30:00+07:00","recorded_at":date+"T15:40:00+07:00","source":"SYNTHETIC TEST","rows":rows}

def expect_error(fn):
    try: fn()
    except (ValueError,AssertionError): return
    raise AssertionError("Lẽ ra phải chặn")

def run_acceptance():
    checks=[]
    def check(label,ok):
        if not ok: raise AssertionError(label)
        checks.append({"Hạng mục":label,"Kết quả":"Đạt"})
    p=POLICY
    x=risk_preview(100e6,100e6,25200.,25000.,750.,0.,0.,0)
    q,u,_=size_order(100e6,100e6,25200.,23500.,0.,0.,p,"R1")
    check("PT03: R1 khớp hàm sizing gốc",q==x["qty"] and u==x["unit_risk"] and q>0 and q%100==0)
    check("PT03: gap qua stop / hết tiền / hết vị thế / heat",all(z["qty"]==0 for z in [
        risk_preview(100e6,100e6,23500.,25000.,750.,0.,0.,0),
        risk_preview(100e6,0.,25200.,25000.,750.,0.,0.,0),
        risk_preview(100e6,100e6,25200.,25000.,750.,0.,0.,5),
        risk_preview(100e6,100e6,25200.,25000.,750.,0.,2.5e6,0),
        risk_preview(100e6,100e6,25200.,25000.,750.,25e6,0.,0)]))
    a=new_account("TEST","2026-11-23T16:00:00+07:00")
    e1=event("2026-11-24",changes={"HPG":{"trend":1,"rs":30.},"FPT":{"trend":1,"rs":20.},"MBB":{"trend":1,"rs":10.}})
    a=append_session(a,e1);r1=replay(a)
    check("PT04: khởi tạo tiền mặt, không mua tại Close tín hiệu",r1["cash"]==p.capital and not r1["orders"] and len(r1["pending"])==3)
    e2=event("2026-11-25",e1,{"HPG":{"trend":-1,"open":25200.,"close":24800.},"FPT":{"open":25100.,"close":26000.},"MBB":{"open":23000.,"close":24000.}})
    a=append_session(a,e2);r2=replay(a)
    check("PT04: mua theo RS60 phiên trước, MBB gap bị chặn",[o["Mã"] for o in r2["orders"]]==["HPG","FPT","MBB"] and [o["Lệnh"] for o in r2["orders"]]==["Mua mô phỏng","Mua mô phỏng","Bỏ mua"])
    check("PT04: giá và giới hạn đúng tại Open",r2["orders"][0]["Open (VND)"]==25200. and r2["cash"]>=0 and len(r2["holdings"])==2 and all(o["Rủi ro (VND)"]<=o["Equity trước mua"]*.005+1e-6 for o in r2["orders"]))
    e3=event("2026-11-26",e2,{"HPG":{"open":24500.,"close":24000.},"FPT":{"close":26200.},"MBB":{"close":25500.}})
    a=append_session(a,e3);r3=replay(a)
    check("PT05: thoát tại Open kế tiếp, không mua đuổi mã đã bỏ",len(r3["trades"])==1 and r3["trades"][0]["Mã"]=="HPG" and r3["orders"][-1]["Lệnh"]=="Bán mô phỏng" and len(r3["holdings"])==1 and r3["holdings"][0]["Mã"]=="FPT")
    b=import_account(export_account(a),"TEST",now="2026-11-27T16:00:00+07:00")
    check("PT05: xuất/khôi phục nhật ký và replay giống nhau",replay(b)==r3)
    wrong=copy.deepcopy(a);wrong["events"][0]["input"]["rows"]["HPG"]["close"]+=1
    expect_error(lambda:replay(wrong))
    expect_error(lambda:import_account(export_account(a),"PAPER",now="2026-11-27T16:00:00+07:00"))
    check("PT05: chặn hash sai và nhập TEST vào PAPER",True)
    m=performance(r3)
    check("PT06: Equity, P&L, MDD và số lệnh nhất quán",m["Số phiên"]==3 and m["Lệnh đóng"]==1 and abs(r3["equity"]-p.capital-r3["daily"][-1]["P&L đã đóng"]-r3["daily"][-1]["P&L mở"])<.01 and m["MDD (%)"]<=0)
    expect_error(lambda:append_session(a,e3))
    missing=event("2026-11-27",e3);missing["previous_session"]="2026-11-25"
    expect_error(lambda:append_session(a,missing))
    revision=event("2026-11-27",e3);revision["rows"]["HPG"]["previous_sha"]=digest("changed")
    expect_error(lambda:append_session(a,revision))
    partial=event("2026-11-27",e3);partial["rows"].pop("HPG")
    expect_error(lambda:append_session(a,partial))
    expect_error(lambda:snapshot_from_report({"identity":("2026-11-23","x","y","TEST")},"2026-11-27T16:00:00+07:00"))
    check("PT07: chặn trùng/thiếu phiên, revision, thiếu mã, TEST",True)
    rr=readiness(r3,"TEST")
    check("PT08: không đủ bằng chứng, không phê duyệt tiền thật",not all(z["Đạt"] for z in rr) and not rr[0]["Đạt"])
    return {"checks":checks,"account":a,"result":r3,"metrics":m,"readiness":rr}
