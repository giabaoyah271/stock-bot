# KT01 + KT02 — Trade Diagnostic & MAE/MFE

Chỉ nghiên cứu khung Ngày, 3 chiến lược V1, SMA50/SMA200, ADX+DI+MACD.
Không thay đổi lệnh, nguồn TCBS, backtesting, phí, T+2, hay baseline tiến cứu.

- Dùng ledger gốc; đối chiếu ngày khớp open kế tiếp và giá/lợi nhuận làm tròn.
- MAE/MFE giá = 100*(giá cực trị/open mua gốc - 1); bao gồm open mua,
  high/low các phiên nắm giữ (bao gồm phiên mua), và chỉ open phiên bán.
  Không dùng high/low/close phiên bán, không dùng giá sau thoát.
- MFE ròng = giá thuận lợi nhất quy đổi bằng cùng phí mua/bán, thuế,
  trượt giá hai chiều; có thể âm nếu lợi thế giá không bù chi phí.
  Không phải lợi nhuận thực tế có thể chắc chắn khớp tại high.
- Giveback = MFE ròng trừ lợi nhuận ròng chính xác tại open bán.
  MAE 3 phiên đầu gồm tối đa 3 phiên theo offset từ phiên mua,
  và open bán nếu bán tại offset 1 hoặc 2.
- Chỉ báo đầu vào lấy ở nến tín hiệu mua. RVOL dùng Vol_Avg hiện có của V1.
- Stop tại tín hiệu mua chỉ là ngưỡng tham chiếu close - 2 ATR, không phải
  lệnh stop khớp thực tế. Nhóm thoát V1 được suy từ quy tắc, không phải nhãn ledger.
- Chỉ phân tích giao dịch đã đóng; không tạo giao dịch giả hoặc tối ưu từ dữ liệu này.
- Nến hôm nay trước 15:15 VN được loại khỏi báo cáo; dữ liệu nguồn vẫn có thể
  trễ hoặc điều chỉnh. Không dùng cho hồ sơ tiến cứu đã khóa.

UI: Backtesting đa mã và kiểm định chiến lược → KT01 + KT02.
Chạy HPG/MBB trước rồi cả 12 mã × 3 chiến lược.
Xuất CSV chi tiết + tổng hợp (và lỗi nếu có).
