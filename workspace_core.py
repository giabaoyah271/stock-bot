"""PT09 presentation/operations adapters. Strategy, risk and journal engines unchanged."""
import hashlib
import pandas as pd
from signal_engine_core import local_now,local_days,END,read_reference,validate_index,scan_batch,report_rows,STATES,U5,BATCHES
from full_universe_core import SHA_B
from trading_dashboard_core import watchlist_frame
from paper_trading_core import snapshot_from_report,append_session

PAGES=("Tổng quan","Cơ hội giao dịch","Phân tích cổ phiếu","Danh mục đầu tư","Cài đặt & Nghiên cứu")
NAV="pt09_page"
REF="pt09_reference_bytes"
PROBE="pt09_index_probe"
REPORT="pt02_report"
SYMBOL="pt09_symbol"
SECTIONS=("Tổng quan","Vị thế","Cơ hội & rủi ro","Nhật ký","Hiệu suất")
ADVANCED=("Thiết lập & sao lưu","Kiểm định KT01–KT18","Bộ quét V1","Phân tích V1 đầy đủ","Kiểm thử tín hiệu PT02","Nghiệm thu tích hợp","Kiểm chứng & sẵn sàng")
def checked_reference(data):
    if hashlib.sha256(data).hexdigest()!=SHA_B: raise ValueError("ZIP không đúng SHA-256 U5-B đã nghiệm thu")
    read_reference(data)
    return bytes(data)

def index_status(ix,now=None):
    t=local_now(now)
    if ix is None or ix.empty: raise ValueError("Không có VN-Index")
    dates=local_days(ix.index)
    last=dates[-1].date()
    before=(t.hour,t.minute)<(15,15)
    if last>t.date() or (last==t.date() and before): raise ValueError("Phiên chưa hoàn tất/ở tương lai")
    if last==t.date(): status="Có nến hôm nay sau mốc 15:15; cần xác nhận đã hoàn tất"
    elif before: status="Chưa đến 15:15; dữ liệu hiển thị phiên trước"
    else: status="Chưa có nến hôm nay; có thể nghỉ giao dịch hoặc dữ liệu chậm"
    if (t.date()-last).days>7: status="Dữ liệu quá 7 ngày – không quét phiên mới"
    return {"last":str(last),"checked_at":t.isoformat(),"status":status,"today":last==t.date()}

def build_report(ref_bytes,ix,loader,scope="ALL",saved=None,now=None,progress=None):
    """Auto-select actual provider last session, no silent fallback or change of policy."""
    if scope not in ("ALL",*BATCHES): raise ValueError("Phạm vi không hợp lệ")
    stamp=local_now(now);probe=index_status(ix,stamp)
    old,zeros,reference=read_reference(ref_bytes)
    index,digest=validate_index(ix,reference,probe["last"],stamp)
    identity=(probe["last"],digest,SHA_B,"LIVE")
    rows=dict(saved["rows"]) if saved and saved.get("identity")==identity and scope!="ALL" else {}
    symbols=U5 if scope=="ALL" else BATCHES[scope]
    for row in scan_batch(symbols,loader,index,old,zeros,stamp,progress):
        rows[row["Mã"]]=row
    return {"identity":identity,"rows":rows,"updated":local_now().isoformat(),"previous_session":str(index.index[-2].date()),
            "previous_index_sha":hashlib.sha256(index.iloc[:-1].to_csv(float_format="%.17g").encode()).hexdigest()}

def opportunities(report=None):
    """Join full watchlist with the original rank, never rerank after filtering."""
    base=watchlist_frame()[["Mã","Ngành (sơ bộ)","Phạm vi KT18","Dữ liệu hồi cứu"]]
    if report and len(report.get("identity",()))==4 and report["identity"][3]=="LIVE" and report.get("rows"):
        d=report_rows(report["rows"].values()).drop(columns=["Ngành"],errors="ignore")
        out=base.merge(d,on="Mã",how="left",validate="one_to_one")
    else: out=base.copy()
    for col in ("Kỹ thuật","Tín hiệu","Hạng mua mới (kỹ thuật)","Close (nghìn VND)","RS60 (đpt)","Buy Score (%)","Sell Score (%)","GTGD proxy 20 (VND)","Lý do","Phiên cuối"):
        if col not in out: out[col]=pd.NA
    out["Kỹ thuật"]=out["Kỹ thuật"].fillna("Chưa quét")
    out["Tín hiệu"]=out["Tín hiệu"].fillna("Chưa xác định")
    for col in ("Hạng mua mới (kỹ thuật)","Close (nghìn VND)","RS60 (đpt)","Buy Score (%)","Sell Score (%)","GTGD proxy 20 (VND)"):
        out[col]=pd.to_numeric(out[col],errors="coerce")
    out["GTGD 20 nến (tỷ VND)"]=out["GTGD proxy 20 (VND)"]/1e9
    return out.sort_values(["Hạng mua mới (kỹ thuật)","Mã"],na_position="last").reset_index(drop=True)

def filter_opportunities(d,query="",sectors=(),signals=(),quality=()):
    out=d
    if query.strip(): out=out[out["Mã"].str.contains(query.strip().upper(),regex=False)]
    if sectors: out=out[out["Ngành (sơ bộ)"].isin(sectors)]
    if signals: out=out[out["Tín hiệu"].isin(signals)]
    if quality: out=out[out["Kỹ thuật"].isin(quality)]
    return out.reset_index(drop=True)

def record_preview(account,report,now=None):
    """Pure validation before explicit confirmation. No TEST/stale data, no backfill."""
    if not account: raise ValueError("Chưa khởi tạo/khôi phục tài khoản Paper")
    if account["header"]["mode"]!="PAPER": raise ValueError("Không dùng tài khoản TEST")
    if not report: raise ValueError("Chưa quét phiên mới")
    event=snapshot_from_report(report,now)
    return append_session(account,event)

def weights(result):
    h=pd.DataFrame(result["holdings"])
    if h.empty: return h,pd.DataFrame(columns=["Ngành","Giá trị Close","Tỷ trọng (%)"])
    h["Tỷ trọng (%)"]=100*h["Giá trị Close"]/result["equity"]
    g=h.groupby("Ngành",as_index=False)["Giá trị Close"].sum()
    g["Tỷ trọng (%)"]=100*g["Giá trị Close"]/result["equity"]
    return h,g
