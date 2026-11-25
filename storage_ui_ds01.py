"""Session adapter: explicit owner login, restore once, fail closed on Paper writes."""
import json
import time
import streamlit as st
from storage_ds01 import Config,SupabaseBackend,Repository,StorageError,json_bytes,sha
from storage_codec_ds01 import encode_report,decode_report,encode_single,decode_single

PREFIX="ds01_"
ACCOUNT="pt0308_paper_account"
REF="pt09_reference_bytes"
REPORT="pt02_report"
SINGLE="pt10_single"
PREF_KEYS=("pt09_page","v3_terminal_group","pt10_detail_symbol","pt10_detail_tf","pt10_detail_range","pt10_panel",
           "pt10_overlays_Ngày","pt10_overlays_1 Giờ","pt10_overlays_Tuần","pt09_scope","pt09_search","pt09_deep",
           "pt09_sectors","pt09_signals","pt09_quality")
def config():
    try: raw=st.secrets.get("supabase")
    except (FileNotFoundError,KeyError): return None
    if raw is None: return None
    try:
        return Config(raw["url"],raw["anon_key"],raw["service_role_key"],raw["owner_id"],raw["namespace"],raw.get("market_storage_allowed",False))
    except Exception: raise StorageError("Cấu hình Supabase thiếu hoặc không hợp lệ") from None

def repo():
    c=config()
    if c is None or not authorized(c): raise StorageError("Chưa cấu hình hoặc chưa xác thực chủ sở hữu")
    return Repository(SupabaseBackend(c))

def authorized(c):
    return st.session_state.get(PREFIX+"owner")==c.owner_id and st.session_state.get(PREFIX+"namespace")==c.namespace and st.session_state.get(PREFIX+"url")==c.url and time.time()<st.session_state.get(PREFIX+"expires",0)

def gate():
    try: c=config()
    except StorageError:
        st.error("Cấu hình Supabase không hợp lệ. Kiểm tra Secrets; không thể truy cập dữ liệu Cloud.")
        st.stop()
    if c is None: return
    if not authorized(c):
        # Never carry a previous owner's data or confirmation into the login screen.
        for k in list(st.session_state):
            if not k.startswith("ds01_login"): del st.session_state[k]
        st.title("Stock Bot · Đăng nhập kho lưu trữ")
        st.caption("Dùng tài khoản Supabase Auth của chủ sở hữu. Không phải tài khoản TCBS.")
        with st.form("ds01_login",clear_on_submit=True):
            email=st.text_input("Email Supabase Auth",key="ds01_login_email")
            password=st.text_input("Mật khẩu Supabase Auth",type="password",key="ds01_login_password")
            submitted=st.form_submit_button("Đăng nhập")
        if submitted:
            try:
                SupabaseBackend(c).authenticate(email,password)
                st.session_state[PREFIX+"owner"]=c.owner_id
                st.session_state[PREFIX+"namespace"]=c.namespace
                st.session_state[PREFIX+"url"]=c.url
                st.session_state[PREFIX+"expires"]=time.time()+3600
                st.rerun()
            except Exception: st.error("Đăng nhập thất bại; kiểm tra tài khoản hoặc kết nối.")
        st.stop()
    if st.sidebar.button("Đăng xuất kho lưu trữ",key="ds01_logout"):
        for k in list(st.session_state): del st.session_state[k]
        st.rerun()

def enabled(kind):
    c=config()
    return c is not None and authorized(c) and (kind=="preferences" or c.market_storage_allowed)

def status(kind,message):
    st.session_state.setdefault(PREFIX+"status",{})[kind]=message

def versions():
    return st.session_state.setdefault(PREFIX+"versions",{})

def save(kind,data):
    if not enabled(kind): return False
    if kind not in versions(): raise StorageError("Chưa xác định phiên bản Cloud; kiểm tra kết nối và tải lại")
    try:
        r=repo()
        versions()[kind]=r.save(kind,data,versions()[kind])
        try: r.b.log(kind,"saved")
        except Exception: pass
        status(kind,"Đã đồng bộ · v"+str(versions()[kind]))
        st.session_state[PREFIX+"last_sync"]=time.strftime("%Y-%m-%d %H:%M:%S UTC",time.gmtime())
        return True
    except Exception as e:
        status(kind,"Đồng bộ thất bại · "+type(e).__name__)
        try: repo().b.log(kind,"failed")
        except Exception: pass
        # Do not expose response bodies, object names, or credentials.
        raise StorageError("Chưa xác nhận lưu Cloud; kiểm tra trạng thái và tải lại trước khi ghi") from None

def safe_pref(k,v):
    if k=="pt09_page":
        from workspace_core import PAGES
        return v in PAGES
    if k=="v3_terminal_group": return v in ("Nghiên cứu","Hệ thống")
    if k=="pt10_detail_symbol": return isinstance(v,str) and len(v)<=10 and v.isalnum()
    if k=="pt10_detail_tf": return v in ("Ngày","1 Giờ","Tuần")
    if k=="pt10_detail_range": return type(v) is int and v in (60,100,200,500)
    if k=="pt10_panel": return v in ("RSI","MACD","ADX / DI","ATR","Không")
    if k.startswith("pt10_overlays_"):
        return isinstance(v,list) and len(v)<=5 and all(x in ("SMA20","SMA50","SMA200","Bollinger","Trailing Stop S0P0") for x in v)
    if k=="pt09_scope": return v in ("ALL","B1","B2","B3","B4")
    if k=="pt09_search": return isinstance(v,str) and len(v)<=50
    if k=="pt09_deep": return type(v) is bool
    if k in ("pt09_sectors","pt09_signals","pt09_quality"):
        return isinstance(v,list) and len(v)<=120 and all(isinstance(x,str) and len(x)<=150 for x in v)
    return False

def restore_one(r,kind):
    v,data=r.load(kind)
    if data is not None:
        if kind=="reference":
            from workspace_core import checked_reference
            st.session_state[REF]=checked_reference(data)
        elif kind=="paper":
            from paper_trading_core import import_account
            st.session_state[ACCOUNT]=import_account(data)
        elif kind=="scan":
            if REF not in st.session_state: raise StorageError("Cần U5-B đã xác minh")
            st.session_state[REPORT]=decode_report(data)
            st.session_state[PREFIX+"restored_scan"]=True
        elif kind=="single":
            if REF not in st.session_state: raise StorageError("Cần U5-B đã xác minh")
            st.session_state[SINGLE]=decode_single(data)
            st.session_state[PREFIX+"restored_single"]=True
        else:
            p=json.loads(data)
            if not isinstance(p,dict): raise StorageError("Tùy chọn không hợp lệ")
            st.session_state[PREFIX+"prefs"]={k:v for k,v in p.items() if k in PREF_KEYS and safe_pref(k,v)}
    elif kind=="paper" and ACCOUNT in st.session_state:
        # Preserve local data for explicit import, but never silently adopt it.
        status(kind,"Cloud chưa có tài khoản; nhập JSON thủ công")
        versions()[kind]=0
        st.session_state[PREFIX+"local_paper_only"]=True
        return
    versions()[kind]=v
    status(kind,"Đã khôi phục · v"+str(v) if v else "Chưa có dữ liệu Cloud")

def initialize(force=False):
    c=config()
    if c is None: return
    if not force and st.session_state.get(PREFIX+"initialized"): return
    st.session_state[PREFIX+"initialized"]=True
    st.session_state[PREFIX+"versions"]={}
    st.session_state[PREFIX+"status"]={}
    try:
        r=repo();r.b.check()
    except Exception:
        status("connection","Không kết nối hoặc bucket chưa Private")
        return
    status("connection","Đã kết nối · Private")
    for kind in ("reference","paper","scan","single","preferences"):
        if not enabled(kind):
            status(kind,"Chưa xác nhận quyền lưu dữ liệu nguồn")
            continue
        try:
            restore_one(r,kind)
            if kind=="paper" and versions().get(kind,0):
                st.session_state.pop(PREFIX+"local_paper_only",None)
        except Exception:
            status(kind,"Khôi phục thất bại; không tự thay thế dữ liệu")
    for k,v in st.session_state.get(PREFIX+"prefs",{}).items():
        if k not in st.session_state: st.session_state[k]=v

def preferences():
    if not enabled("preferences") or "preferences" not in versions(): return
    old=st.session_state.get(PREFIX+"prefs",{})
    p=dict(old)
    for k in PREF_KEYS:
        if k in st.session_state and safe_pref(k,st.session_state[k]): p[k]=st.session_state[k]
        elif k not in st.session_state and k in old: st.session_state[k]=old[k]
    if p==old: return
    signature=sha(json_bytes(p))
    if st.session_state.get(PREFIX+"prefs_failed")==signature: return
    try:
        save("preferences",json_bytes(p))
        st.session_state[PREFIX+"prefs"]=p
        st.session_state.pop(PREFIX+"prefs_failed",None)
    except StorageError:
        st.session_state[PREFIX+"prefs_failed"]=signature

def persist_reference(data):
    from workspace_core import checked_reference
    data=checked_reference(data)
    st.session_state[REF]=data
    try: save("reference",data)
    except StorageError: status("reference","U5-B chỉ có trong session; chưa lưu Cloud")

def persist_account(account,allow_local_replace=False):
    from paper_trading_core import export_account,import_account
    data=export_account(account)
    import_account(data)
    if enabled("paper"):
        if st.session_state.get(PREFIX+"local_paper_only") and not allow_local_replace:
            raise StorageError("Cloud chưa có tài khoản; xuất rồi nhập JSON để chuyển dữ liệu")
        save("paper",data)
        st.session_state.pop(PREFIX+"local_paper_only",None)
    st.session_state[ACCOUNT]=account

def persist_scan(report):
    st.session_state[REPORT]=report
    st.session_state[PREFIX+"restored_scan"]=False
    if enabled("scan"):
        try: save("scan",encode_report(report))
        except Exception: status("scan","Báo cáo chỉ có trong session; chưa lưu Cloud")

def persist_single(single):
    st.session_state[SINGLE]=single
    st.session_state[PREFIX+"restored_single"]=False
    if enabled("single"):
        try: save("single",encode_single(single))
        except Exception: status("single","Biểu đồ chỉ có trong session; chưa lưu Cloud")

def restored_scan():
    return bool(st.session_state.get(PREFIX+"restored_scan"))

def sidebar_status():
    c=config()
    if c is None:
        st.sidebar.caption("Lưu trữ: chỉ session · chưa cấu hình Supabase")
        return
    s=st.session_state.get(PREFIX+"status",{})
    st.sidebar.caption("Cloud: "+s.get("connection","Chưa kiểm tra"))
    if not c.market_storage_allowed: st.sidebar.warning("Chưa cho phép lưu dữ liệu nguồn; U5-B/Paper/scan chỉ trong session.")
    for k in ("reference","paper","scan"):
        if k in s: st.sidebar.caption(k+": "+s[k])

def render_storage():
    st.subheader("Lưu trữ & đồng bộ")
    c=config()
    if c is None:
        st.info("Chưa cấu hình Supabase. Dữ liệu vẫn chỉ trong session; tiếp tục tải JSON riêng tư.")
        return
    st.caption("Namespace: "+c.namespace+" · Private Storage · PostgreSQL")
    if not c.market_storage_allowed:
        st.warning("Chưa xác nhận quyền lưu dữ liệu TCBS trên Cloud. Chỉ đồng bộ tùy chọn giao diện.")
    s=st.session_state.get(PREFIX+"status",{})
    for kind,label in (("connection","Kết nối"),("reference","U5-B"),("paper","Paper Trading"),("scan","Báo cáo quét"),("single","Biểu đồ riêng"),("preferences","Tùy chọn")):
        st.write(label+" — "+s.get(kind,"Chưa kiểm tra"))
    if REF in st.session_state: st.caption("SHA-256 U5-B: "+sha(st.session_state[REF]))
    if ACCOUNT in st.session_state:
        events=st.session_state[ACCOUNT]["events"]
        st.caption("Phiên Paper cuối: "+(events[-1]["input"]["session"] if events else "Chưa ghi phiên"))
    if REPORT in st.session_state: st.caption("Phiên quét: "+str(st.session_state[REPORT]["identity"][0]))
    st.caption("Lần lưu xác nhận: "+st.session_state.get(PREFIX+"last_sync","Chưa lưu trong session này"))
    if st.button("Kiểm tra dung lượng / nhật ký",key="ds01_usage_btn"):
        try:
            r=repo()
            st.session_state[PREFIX+"usage"]=r.b.usage()
            st.session_state[PREFIX+"logs"]=r.b.logs()
        except Exception: st.error("Không đọc được dung lượng hoặc nhật ký")
    usage=st.session_state.get(PREFIX+"usage")
    if usage is not None:
        st.metric("Dung lượng namespace",f"{usage/1e6:,.2f} MB")
        st.progress(min(1.0,usage/1e9),text="So với 1 GB Storage Free; không phải tổng dung lượng project.")
        if usage>=950_000_000: st.error("Đã dùng ít nhất 95% hạn mức tham khảo; kiểm tra Dashboard.")
        elif usage>=800_000_000: st.warning("Đã dùng ít nhất 80% hạn mức tham khảo.")
    if st.session_state.get(PREFIX+"logs"): st.dataframe(st.session_state[PREFIX+"logs"],hide_index=True,use_container_width=True)
    if st.button("Kiểm tra kết nối / tải lại Cloud",key="ds01_retry"):
        st.session_state.pop(PREFIX+"prefs_failed",None)
        # Invalidate reports and confirmations before restore; never leave an old LIVE report recordable.
        for k in (REPORT,SINGLE,"pt09_op_confirm","pt09_scan_confirm","pt09_recorded","pt09_replace"):
            st.session_state.pop(k,None)
        st.session_state[PREFIX+"restored_scan"]=True
        initialize(force=True)
        st.rerun()
    if enabled("reference") and REF in st.session_state and st.button("Lưu U5-B đang dùng lên Cloud",key="ds01_save_ref"):
        persist_reference(st.session_state[REF]);st.rerun()
    if enabled("paper") and ACCOUNT in st.session_state and st.button("Sao lưu tài khoản hiện hành",key="ds01_backup"):
        try:
            # Manual backup may not promote a local or stale account over a newer head.
            r=repo();v,data=r.load("paper")
            from paper_trading_core import export_account
            if data is None or v!=versions().get("paper") or sha(data)!=sha(export_account(st.session_state[ACCOUNT])):
                raise StorageError("Tài khoản chưa đồng bộ; dùng nhập JSON có xác nhận")
            st.success("Phiên bản hiện hành đã lưu bất biến; tải JSON riêng để có bản sao độc lập.")
        except Exception: st.error("Không xác nhận được bản sao Cloud; tải JSON riêng.")
    if enabled("paper") and st.button("Xem lịch sử sao lưu Paper",key="ds01_history_btn"):
        try: st.session_state[PREFIX+"history"]=repo().b.history("paper")
        except Exception: st.error("Không đọc được lịch sử")
    history=st.session_state.get(PREFIX+"history",[])
    if history:
        st.dataframe(history,hide_index=True,use_container_width=True)
        v=st.selectbox("Phiên bản cần tải",tuple(int(x["version"]) for x in history),key="ds01_restore_version")
        if st.button("Tải phiên bản JSON để khôi phục thủ công",key="ds01_download_version"):
            try:
                from paper_trading_core import import_account
                _,data=repo().load("paper",v)
                import_account(data)
                st.session_state[PREFIX+"download"]=data
            except Exception: st.error("Không xác minh được phiên bản")
        if st.session_state.get(PREFIX+"download"):
            st.download_button("Tải JSON đã xác minh",st.session_state[PREFIX+"download"],"paper_backup.json","application/json",key="ds01_dl")
        st.caption("Khôi phục: nhập JSON tại Tài khoản và sao lưu, xác nhận thay thế. Không tự quay lùi lịch sử.")
    st.caption("Không tự xóa snapshot. Kiểm tra hạn mức thực tế tại Supabase Dashboard; tiếp tục sao lưu JSON riêng.")
