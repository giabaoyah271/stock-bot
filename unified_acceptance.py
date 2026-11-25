"""PT10 frozen data acceptance; no provider calls and no Paper account writes."""
import pandas as pd
from signal_engine_core import read_reference,report_rows,END
from unified_strategy_core import COHORT,frozen_snapshot,chart_from_report,transition_history,reference_stop
from full_universe_core import SHA_B
import hashlib

def run_unified_acceptance(ref_bytes,progress=None):
    old,zeros,index=read_reference(ref_bytes)
    rows={};charts={}
    for i,s in enumerate(COHORT):
        d,r=frozen_snapshot(s,old,index)
        if not d["Trend"].equals(old[s]["Trend"].astype(d["Trend"].dtype)): raise ValueError(s+": lịch sử Trend khác")
        charts[s]=d;rows[s]=r
        if progress: progress(i+1,len(COHORT),s)
    # A TEST-only adapter for chart parity, never placed in session/report used by Paper.
    h=hashlib.sha256(index.to_csv(float_format="%.17g").encode()).hexdigest()
    internal={"identity":(str(END.date()),h,SHA_B,"LIVE"),"rows":rows,"charts":charts}
    ranks=report_rows(rows.values()).set_index("Mã")
    out=[]
    for s in COHORT:
        d,r=chart_from_report(internal,s)
        transitions=transition_history(d)
        expected=old[s]["Trend"].shift().notna() & old[s]["Trend"].ne(old[s]["Trend"].shift())
        if not transitions.index.equals(old[s].index[expected]): raise ValueError(s+": lịch sử chuyển trạng thái khác")
        rank=ranks.at[s,"Hạng mua mới (kỹ thuật)"]
        out.append({"Mã":s,"Phiên":str(END.date()),"Tín hiệu":r["Tín hiệu"],"Trend trước":r["Trend trước"],"Trend":r["Trend"],
                    "Close (nghìn VND)":r["Close (nghìn VND)"],"RS60 (đpt)":r["RS60 (đpt)"],"Buy Score (%)":r["Buy Score (%)"],
                    "Sell Score (%)":r["Sell Score (%)"],"Hạng mua mới (kỹ thuật)":rank,"Số lần chuyển trạng thái":len(transitions),
                    "Stop tham chiếu R1 (nghìn VND)":reference_stop(d),"SHA lịch sử":r["SHA lịch sử"],"Đối chiếu":"Khớp",
                    "Chế độ":"KIỂM THỬ HỒI CỨU"})
    return pd.DataFrame(out)
