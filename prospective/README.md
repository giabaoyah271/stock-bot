# Stock Bot: mốc đối chứng cố định và kiểm định tiến cứu

**Trạng thái:** Đã khóa **cấu hình tham chiếu** bằng commit GitHub bất biến
[`415b6ca728bbfb57903fde7b7dcf0a96443920bf`](https://github.com/giabaoyah271/stock-bot/commit/415b6ca728bbfb57903fde7b7dcf0a96443920bf)
ngày **23/11/2026 (giờ Việt Nam)**. Chi tiết tại [`baseline.json`](baseline.json).
Các commit tài liệu và kiểm thử sau mốc này không sửa quy tắc giao dịch.

> **Chưa có kết quả tiến cứu.** Dữ liệu đến hết 23/11/2026 đã được dùng
> trong quá trình nghiên cứu. Kiểm định tiến cứu chỉ bắt đầu với **phiên giao
> dịch đã hoàn tất đầu tiên sau 23/11/2026** được lưu bằng bằng chứng
> cùng thời điểm. Nếu 24/11/2026 không giao dịch hoặc chưa có bản ghi,
> không được tự gán ngày đó là một kết quả tiến cứu.

## 1. Cố định phương pháp

- 12 mã: HPG, MBB, FPT, TCB, MWG, VNM, ACB, DGC, GAS, GMD, PNJ, REE.
- 5 chiến lược: V1, SMA50/SMA200, ADX + DI + MACD, V2, V2.1 xác nhận MACD.
- Dùng giá OHLCV khung Ngày từ bộ nạp TCBS hiện có; có thể sử dụng lịch sử
  trước ngày khóa để tính các chỉ báo, **không** tính những phiên đó là
  quan sát tiến cứu.
- Tín hiệu ở cuối phiên hoàn tất; giả định khớp giá mở cửa phiên kế tiếp.
  Giữ nguyên phí và trượt giá, quy tắc tái đầu tư, Equity và PF như
  `baseline.json`. Không áp đặt thêm T+2/T+3 trong mô phỏng.
- Không thay đổi ngưỡng, trọng số hoặc phương pháp trong thời gian đánh
  giá. Nếu thay đổi, ghi thành **phiên bản mới**, không trộn kết quả.

## 2. Cách ghi nhận đơn giản, không thêm giao diện hay cơ sở dữ liệu

Mỗi lần thực hiện **thủ công**, sau khi phiên giao dịch kết thúc và
dữ liệu nguồn đã hoàn chỉnh:

1. Truy cập ứng dụng Streamlit đang chạy đúng phiên bản chiến lược đối
   chứng (kiểm tra commit/sha mã ở `baseline.json`). Vào **Backtesting
   đa mã và kiểm định chiến lược → Tổng hợp Equity và Drawdown đa mã**.
2. Chọn **Cả 12 mã** và **Tất cả 5 chiến lược**, nhấn **Chạy tổng hợp rủi ro**.
   Tải CSV `stock_bot_rui_ro_da_ma.csv`. Kiểm tra cột **Dữ liệu nguồn đến**
   đã thuộc phiên hoàn tất. Không dùng nến còn đang chạy.
3. Lưu **bản CSV gốc không chỉnh sửa** trong thư mục lưu trữ riêng tư,
   đặt tên `YYYY-MM-DD_stock_bot_rui_ro_da_ma.csv`. Không cần đưa
   dữ liệu giá TCBS hoặc kết quả chi tiết lên repo công khai.
4. Tính mã SHA-256 của **tệp CSV gốc** bằng công cụ tin cậy trên máy
   dùng để lưu tệp, rồi ghi một dòng vào bản sao `records_template.csv`.
   Lưu thời điểm ghi, ngày phiên cuối, commit, tên tệp và hash.
5. Chỉ thêm bản ghi, không ghi đè các tệp/bản ghi cũ. Nếu nguồn TCBS có
   điều chỉnh số liệu, lưu bản mới như một **revision**, giữ bản cũ và
   ghi chú lý do. Nếu bỏ lỡ một phiên, ghi rõ thiếu bằng chứng và không
   gọi việc tái chạy lịch sử là quan sát được chốt đúng thời điểm.

**Lưu ý:** CSV rủi ro hiện tại ghi **kết quả mô phỏng tính lại trên toàn
lịch sử** tại thời điểm tải; nó chưa phải nhật ký dự báo/tín hiệu được
ghi bất biến theo từng phiên. Việc lưu từng ảnh chụp CSV kèm hash cung cấp
vết kiểm chứng thời điểm và phát hiện thay đổi dữ liệu/phiên bản,
nhưng **không tự chứng minh** khả năng khớp lệnh thực tế hay loại trừ mọi
sai lệch nguồn dữ liệu.

## 3. Đánh giá kết quả sau khi có dữ liệu mới

- Sử dụng **cùng một baseline** và chuỗi bằng chứng không chỉnh sửa;
  không dùng kết quả các phiên mới để sửa ngưỡng của cùng đợt kiểm định.
- Tách riêng hiệu quả tiến cứu kể từ phiên đủ điều kiện đầu tiên và hiệu
  quả lịch sử 2022–2026; không suy diễn từ PF toàn lịch sử sang PF tiến cứu.
- Khi so sánh danh mục, không xem trung bình lợi nhuận từng mã là lợi
  nhuận của danh mục thực tế.
- Cần thêm đánh giá giá điều chỉnh, cổ tức, tính thanh khoản, khả năng
  khớp lệnh, yếu tố sống sót của danh sách cổ phiếu và thay đổi lịch sử
  dữ liệu trước khi sử dụng cho quyết định tiền thật.
- Nếu không có snapshot trong một phiên, chỉ có thể gọi việc chạy lại
  phiên đó là **backtest hồi cứu**, không phải kết quả tiến cứu được
  quan sát và lưu đúng thời điểm.

## 4. Giới hạn và các bước kế tiếp

Đợt này chỉ thêm bài kiểm thử và tài liệu, **không** sửa `backtesting.py`,
chiến lược, UI Streamlit, TCBS, khung 1 Giờ hoặc cảnh báo khung Tuần.
Nhánh `main` được giữ nguyên. Các bài kiểm thử cần được chạy đầy đủ
trên bản checkout của repo; nếu chưa có môi trường thực thi đầy đủ, không
ghi nhận là đã đạt.

Sau khi bộ kiểm thử nhân quả/khớp lệnh đạt trên toàn repo và đã có một
chuỗi quan sát tiến cứu, mới nghiên cứu nguyên nhân lỗ V2/V2.1, trên
tập phát triển riêng, rồi kiểm định phiên bản mới ở giai đoạn khác.
