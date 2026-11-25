"""PT01 presentation model: no quotes, trade recommendations or account state."""
import pandas as pd
from universe_u5 import U5, U5_VERSION
from universe_prepare_core import SECTORS, ZERO_COUNTS, SHORT
from full_universe_core import ADDITIONS, UNAVAILABLE
from portfolio_core import Policy

HOME="Tổng quan Trading"
WATCHLIST="Watchlist U5 (120 mã)"
DETAIL="Phân tích chi tiết mã"
SIGNALS="Quét U5 – S0P0 / RS60"
SCAN="Quét tín hiệu toàn thị trường"
PORTFOLIO="Danh mục & Nhật ký"
PERFORMANCE="Hiệu suất & Kiểm chứng"
RESEARCH_PAGE="Backtesting đa mã và kiểm định chiến lược"
PAGES=(HOME,SIGNALS,WATCHLIST,DETAIL,SCAN,PORTFOLIO,PERFORMANCE,RESEARCH_PAGE)
NAV_KEY="pt01_page"
LABELS={SCAN:"Quét tín hiệu V1 (danh sách cũ)",RESEARCH_PAGE:"Trung tâm kiểm định KT01–KT18"}
CANDIDATE="U5-A0-RS60-P5-R050"
HISTORY_END="2026-11-23"
HISTORY_OK="Có trong mẫu hồi cứu"
HISTORY_PREFIX="Mẫu hồi cứu rút ngắn"
HISTORY_ZERO="Mẫu hồi cứu nến có giao dịch"
HISTORY_SHORT="Thiếu 200 nến tại mốc nghiên cứu"
HISTORY_ERROR="Chưa đạt dữ liệu hồi cứu"
HISTORY_GROUPS=(HISTORY_OK,HISTORY_PREFIX,HISTORY_ZERO,HISTORY_SHORT,HISTORY_ERROR)

def watchlist_frame():
    """Historical coverage only; no claim of present market data or buy eligibility."""
    rows=[]
    for s in U5:
        if s in SHORT: status=HISTORY_SHORT
        elif s in UNAVAILABLE: status=HISTORY_ERROR
        elif s=="ACV" or s in ADDITIONS: status=HISTORY_PREFIX
        elif s in ZERO_COUNTS: status=HISTORY_ZERO
        else: status=HISTORY_OK
        rows.append({"Mã":s,"Ngành (sơ bộ)":SECTORS[s],
                     "Phạm vi KT18":"Ngoài mẫu" if s in UNAVAILABLE else "Trong mẫu U5-B",
                     "Dữ liệu hồi cứu":status,"Mốc hồi cứu":HISTORY_END,
                     "Dữ liệu hiện tại":"Chưa kiểm tra",
                     "Tuân thủ":"Chưa xác minh đầy đủ",
                     "Điều kiện mua":"Chưa phê duyệt"})
    return pd.DataFrame(rows)

def filter_watchlist(query="",sectors=(),statuses=()):
    d=watchlist_frame()
    q=query.strip().upper()
    if q: d=d[d["Mã"].str.contains(q,regex=False)]
    if sectors: d=d[d["Ngành (sơ bộ)"].isin(sectors)]
    if statuses: d=d[d["Dữ liệu hồi cứu"].isin(statuses)]
    return d.reset_index(drop=True)

def candidate_parameters():
    p=Policy()
    return pd.DataFrame([
        ("Chiến lược nền","S0P0 – SMA50/SMA200"),
        ("Bộ lọc / xếp hạng","A0 / RS60 (sau đó Buy Score, mã)"),
        ("Position Sizing","R1"),
        ("Khung chính","Ngày"),
        ("Vốn khởi tạo giả định",f"{int(p.capital):,} VND"),
        ("Vị thế tối đa",str(p.max_positions)),
        ("Rủi ro dự kiến/lệnh",f"{p.risk:.2%}"),
        ("Tỷ trọng mã khi mua",f"{p.stock_cap:.0%}"),
        ("Tỷ trọng ngành khi mua",f"{p.sector_cap:.0%}"),
        ("Portfolio Heat ban đầu",f"{p.heat_cap:.1%}"),
        ("Lô giao dịch",str(p.lot)),
        ("Khớp mô phỏng","Open nến giao dịch tiếp theo"),
        ("Margin","Không"),
    ],columns=["Thông số ứng viên","Thiết lập nghiên cứu"])
