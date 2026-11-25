"""PT09 offline functional acceptance, no TCBS, no actual account changes."""
import copy
import pandas as pd
from unittest.mock import patch
from workspace_core import PAGES,ADVANCED,SECTIONS,checked_reference,index_status,build_report,opportunities,filter_opportunities,record_preview,weights
from paper_acceptance import run_acceptance,event,expect_error
from paper_trading_core import COHORT,new_account,replay,digest
from signal_engine_core import U5,END
from full_universe_core import SHA_B

def run_workspace_acceptance():
    old=run_acceptance()
    checks=list(old["checks"])
    def check(label,ok):
        if not ok: raise AssertionError(label)
        checks.append({"Hạng mục":label,"Kết quả":"Đạt"})
    check("PT09: 5 trang chính, 7 mục nâng cao, 5 tab danh mục",len(set(PAGES))==5 and len(set(ADVANCED))==7 and len(set(SECTIONS))==5)
    d=opportunities()
    check("PT09: Watchlist chưa quét vẫn đủ 120, không tạo giá/tín hiệu giả",len(d)==120 and d["Close (nghìn VND)"].isna().all() and (d["Tín hiệu"]=="Chưa xác định").all())
    rows={}
    for s,rs,score in [("HPG",10.,60.),("FPT",20.,70.)]:
        rows[s]={"Mã":s,"Kỹ thuật":"Khớp mẫu KT18","Tín hiệu":"Mua mới (tín hiệu)","RS60 (đpt)":rs,"Buy Score (%)":score}
    report={"identity":("2026-11-25",digest("idx"),SHA_B,"LIVE"),"rows":rows}
    d=opportunities(report)
    filtered=filter_opportunities(d,"HPG")
    check("PT09: lọc bảng không làm thay đổi hạng gốc; mã chưa quét không có hạng",len(d)==120 and d.iloc[0]["Mã"]=="FPT" and int(filtered.iloc[0]["Hạng mua mới (kỹ thuật)"])==2 and d["Hạng mua mới (kỹ thuật)"].notna().sum()==2)
    test=copy.deepcopy(report);test["identity"]=(*report["identity"][:3],"TEST")
    check("PT09: bảng giao dịch không hiển thị kết quả TEST",opportunities(test)["Hạng mua mới (kỹ thuật)"].isna().all())
    ix=pd.DataFrame({"close":[100.]},index=pd.DatetimeIndex(["2026-11-23"]))
    x=index_status(ix,"2026-11-25T14:30:00+07:00");y=index_status(ix,"2026-11-25T16:00:00+07:00")
    check("PT09: hiển thị đúng ngày TCBS, không tự suy diễn nghỉ lễ",x["last"]=="2026-11-23" and not y["today"] and "có thể" in y["status"])
    future=ix.copy();future.index=pd.DatetimeIndex(["2026-11-25"])
    expect_error(lambda:index_status(future,"2026-11-25T14:30:00+07:00"))
    expect_error(lambda:checked_reference(b"wrong ZIP"))
    check("PT09: chặn phiên chưa hoàn tất và sai SHA tham chiếu",True)
    # Exercise the adapter using mocked data source; no downloaded data.
    cal=pd.DatetimeIndex(["2026-11-23","2026-11-25"],name="Ngày")
    idx=pd.Series([100.,101.],index=cal,name="close")
    ix=pd.DataFrame({"close":idx})
    with patch("workspace_core.read_reference",return_value=({}, {},idx.iloc[:1])),patch("workspace_core.validate_index",return_value=(idx,digest("index"))),patch("workspace_core.scan_batch",return_value=[{"Mã":"HPG"}]):
        r=build_report(b"mock",ix,lambda s:None,now="2026-11-25T16:00:00+07:00")
    check("PT09: adapter tự chọn phiên cuối và giữ cấu trúc báo cáo Paper",r["identity"][0]=="2026-11-25" and r["identity"][3]=="LIVE" and r["previous_session"]=="2026-11-23")
    account=new_account("PAPER","2026-11-25T16:00:00+07:00")
    e=event("2026-11-26",changes={"HPG":{"trend":1}})
    raw={}
    for s in U5:
        if s not in COHORT: raw[s]={"Mã":s,"Kỹ thuật":"Ngoài mẫu"};continue
        q=e["rows"][s]
        raw[s]={"Mã":s,"Kỹ thuật":"Khớp mẫu KT18","Phiên cuối":"2026-11-26","Chế độ":"QUÉT PHIÊN MỚI","Ghi nhận (VN)":"2026-11-26T15:25:00+07:00",
                "Open (nghìn VND)":q["open"]/1000,"Close (nghìn VND)":q["close"]/1000,"ATR (nghìn VND)":q["atr"]/1000,"Trend trước":q["prev"],"Trend":q["trend"],
                "RS60 (đpt)":q["rs"],"Buy Score (%)":q["score"],"SHA lịch sử":q["sha"],"SHA lịch sử trước phiên":q["previous_sha"]}
    mock={"identity":("2026-11-26",e["index_sha"],SHA_B,"LIVE"),"rows":raw,"updated":"2026-11-26T15:30:00+07:00",
          "previous_session":e["previous_session"],"previous_index_sha":e["previous_index_sha"]}
    now="2026-11-26T15:40:00+07:00"
    nxt=record_preview(account,mock,now)
    check("PT09: ghi phiên qua engine gốc, bản xem trước không sửa tài khoản",len(account["events"])==0 and len(nxt["events"])==1 and replay(nxt)["cash"]==100e6)
    expect_error(lambda:record_preview(nxt,mock,now))
    expect_error(lambda:record_preview(account,mock,"2026-11-27T16:00:00+07:00"))
    bad=copy.deepcopy(mock);bad["rows"].pop("HPG")
    expect_error(lambda:record_preview(account,bad,now))
    bad=copy.deepcopy(mock);bad["identity"]=(*mock["identity"][:3],"TEST")
    expect_error(lambda:record_preview(account,bad,now))
    check("PT09: chặn ghi trùng, phiên cũ, thiếu mã và TEST",True)
    h,g=weights(old["result"])
    check("PT09: tỷ trọng mã/ngành khớp giá trị danh mục",len(h)==1 and abs(h["Tỷ trọng (%)"].sum()-g["Tỷ trọng (%)"].sum())<1e-9 and abs(h["Tỷ trọng (%)"].sum()-100*h["Giá trị Close"].sum()/old["result"]["equity"])<1e-9)
    return {"checks":checks,"paper_test":old}
