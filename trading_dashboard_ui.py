"""PT01 Streamlit navigation and read-only workspace; no order execution."""
import streamlit as st
from trading_dashboard_core import (
    HOME,WATCHLIST,DETAIL,SCAN,PORTFOLIO,PERFORMANCE,RESEARCH_PAGE,NAV_KEY,
    CANDIDATE,HISTORY_END,HISTORY_GROUPS,watchlist_frame,filter_watchlist,candidate_parameters
)
from universe_u5 import U5_VERSION
from portfolio_core import Policy

def go_to(page):
    st.session_state[NAV_KEY]=page

def jump(label,page,key):
    st.button(label,key=key,on_click=go_to,args=(page,),use_container_width=True)

def render_overview():
    st.title("Stock Bot V3")
    st.caption("Không gian nghiên cứu và hỗ trợ quyết định giao dịch | PT01")
    st.warning("Chưa có tài khoản Paper Trading hoạt động. Không gửi lệnh, không phê duyệt mua. Các thông số dưới đây là cấu hình nghiên cứu, không phải số dư hay vị thế thực.")
    p=Policy()
    d=watchlist_frame()
    a,b,c,e=st.columns(4)
    a.metric("Watchlist U5",len(d))
    b.metric("Mẫu hồi cứu U5-B",int((d["Phạm vi KT18"]=="Trong mẫu U5-B").sum()))
    c.metric("Vốn khởi tạo giả định",f"{p.capital/1e6:.0f} triệu")
    e.metric("Vị thế tối đa (cấu hình)",str(p.max_positions))
    st.caption(f"Dữ liệu hồi cứu đến {HISTORY_END}. Không có báo giá hiện tại trên trang này.")
    st.subheader("Không gian làm việc")
    left,right=st.columns(2)
    with left:
        st.markdown("**Watchlist U5**")
        st.caption("Tra cứu 120 mã, ngành sơ bộ và phạm vi dữ liệu hồi cứu.")
        jump("Mở Watchlist",WATCHLIST,"pt01_home_watch")
        st.markdown("**Phân tích kỹ thuật**")
        st.caption("Biểu đồ và chỉ báo gốc; hỗ trợ Ngày, 1 Giờ, Tuần.")
        jump("Phân tích một mã",DETAIL,"pt01_home_detail")
        st.markdown("**Trung tâm kiểm định**")
        st.caption("Giữ các kiểm định KT01–KT18 và các báo cáo trước đây.")
        jump("Mở trung tâm kiểm định",RESEARCH_PAGE,"pt01_home_research")
    with right:
        st.markdown("**Bộ quét V1 hiện có**")
        st.caption("Danh sách quét cũ; không phải bộ quét U5-A0-RS60.")
        jump("Mở bộ quét V1",SCAN,"pt01_home_scan")
        st.markdown("**Danh mục và nhật ký**")
        st.caption("Chưa khởi tạo tài khoản mô phỏng; trạng thái triển khai PT03–PT05.")
        jump("Xem trạng thái danh mục",PORTFOLIO,"pt01_home_portfolio")
        st.markdown("**Hiệu suất và kiểm chứng**")
        st.caption("PT06–PT08 chưa triển khai; không hiển thị Equity giả.")
        jump("Xem trạng thái kiểm chứng",PERFORMANCE,"pt01_home_performance")
    st.subheader("Ứng viên kiểm chứng")
    st.markdown(f"**{CANDIDATE}**")
    st.dataframe(candidate_parameters(),hide_index=True,use_container_width=True)
    st.caption("Ngân sách rủi ro không đảm bảo mức lỗ tối đa. Chưa đóng băng ứng viên mới cho kiểm chứng tiến tới; chưa xác minh pháp lý toàn bộ U5.")

def render_watchlist():
    st.title("Watchlist U5")
    st.caption(f"Phiên bản {U5_VERSION} | Mốc hồi cứu {HISTORY_END}")
    d=watchlist_frame()
    a,b,c=st.columns(3)
    a.metric("Mã theo dõi",len(d))
    b.metric("Trong mẫu KT18",int((d["Phạm vi KT18"]=="Trong mẫu U5-B").sum()))
    c.metric("Ngoài mẫu KT18",int((d["Phạm vi KT18"]=="Ngoài mẫu").sum()))
    st.info("Đây là danh sách ứng viên, không phải danh sách đã đủ điều kiện mua hiện tại. Ngành là phân nhóm nghiên cứu sơ bộ. CC1, NAB, VBB, DMX, GEL vẫn được theo dõi; lý do ngoài mẫu chỉ phản ánh dữ liệu tại mốc hồi cứu.")
    q=st.text_input("Tìm mã cổ phiếu",placeholder="Ví dụ: HPG",key="pt01_watch_query")
    left,right=st.columns(2)
    with left:
        sectors=st.multiselect("Ngành (sơ bộ)",sorted(d["Ngành (sơ bộ)"].unique()),key="pt01_watch_sectors")
    with right:
        statuses=st.multiselect("Trạng thái dữ liệu hồi cứu",HISTORY_GROUPS,key="pt01_watch_status")
    out=filter_watchlist(q,sectors,statuses)
    st.caption(f"Hiển thị {len(out)}/{len(d)} mã")
    st.dataframe(out,hide_index=True,use_container_width=True,height=520)
    st.download_button("Tải CSV danh sách đang hiển thị",out.to_csv(index=False).encode("utf-8-sig"),"stock_bot_u5_watchlist.csv","text/csv",key="pt01_watch_csv")
    with st.expander("Giải thích phạm vi"):
        st.write("Có trong mẫu hồi cứu không đồng nghĩa đủ 200 nến tại thời điểm hiện tại. 10 mã có lịch sử rút ngắn (ACV và 9 mã bổ sung); 4 mã sử dụng mẫu nến có giao dịch. Các trạng thái hiện tại và tuân thủ cần được kiểm tra ở bước PT02.")
    jump("Về tổng quan",HOME,"pt01_watch_home")

def render_portfolio_status():
    st.title("Danh mục & Nhật ký")
    st.info("Chưa khởi tạo tài khoản Paper Trading. Không có dữ liệu số dư, vị thế hoặc lịch sử lệnh để hiển thị.")
    st.subheader("Thông số ứng viên (chỉ đọc)")
    st.dataframe(candidate_parameters(),hide_index=True,use_container_width=True)
    st.subheader("Chức năng sẽ triển khai")
    st.write("PT03 — Risk Manager: tính quy mô vị thế từ dữ liệu và ngân sách rủi ro.")
    st.write("PT04 — Portfolio Manager: tiền mặt, vị thế, tỷ trọng và ngân sách rủi ro.")
    st.write("PT05 — Nhật ký Paper Trading: ghi nhận giao dịch mô phỏng theo thời gian, không gửi lệnh thật.")
    jump("Về tổng quan",HOME,"pt01_port_home")

def render_performance_status():
    st.title("Hiệu suất & Kiểm chứng")
    st.warning("Chưa có nhật ký Paper Trading hoặc chuỗi Equity tiến tới. Không hiển thị lợi nhuận hồi cứu như hiệu suất thực tế.")
    st.write("PT06 — Dashboard hiệu suất từ nhật ký mô phỏng đã ghi nhận.")
    st.write("PT07 — Đóng băng cấu hình ứng viên và thu thập dữ liệu tiến tới độc lập.")
    st.write("PT08 — Đánh giá mức sẵn sàng, gồm điều kiện dữ liệu, tuân thủ và rủi ro.")
    jump("Xem Backtesting KT01–KT18",RESEARCH_PAGE,"pt01_perf_research")
    jump("Về tổng quan",HOME,"pt01_perf_home")
