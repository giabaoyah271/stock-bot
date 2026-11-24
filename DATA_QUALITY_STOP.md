# KT04 / KT05 – research-v3

- KT05 chỉ áp dụng dữ liệu khung Ngày từ get_data trước calculate_indicators.
  Kiểm tra time, OHLCV, NaN/inf, giá không dương, khối lượng âm, trùng ngày
  VN, thứ tự, ngày tương lai và tối thiểu 200 nến đã hoàn tất.
  Không tự sắp xếp, điền thiếu hay loại nến lỗi lịch sử; chặn toàn bộ mã.
  Khối lượng bằng 0 cảnh báo, không tự xóa. Không xác nhận lịch giao dịch,
  dữ liệu điều chỉnh cổ tức/chia tách hoặc khớp lệnh thực tế.
  Trước 15:15 VN bỏ nến cùng ngày, sau mốc này vẫn phụ thuộc dữ liệu nhà cung cấp.
  Cache 600 giây giữ nguyên; có thể cần chờ dữ liệu mới sau giờ đóng cửa.
- KT04 ghi trực tiếp state Trailing Stop V1, chỉ bật cho khung Ngày.
  V1_Stop_Age tính từ nến tín hiệu mua (offset 0), không phải phiên khớp.
  V1_Stop_Eligible phản ánh điều kiện offset >= 3; không thay đổi quy tắc.
  V1_Stop_Exit ghi ngưỡng của nến thoát do stop. Khi đứng ngoài không có
  stop đang hoạt động. Biểu đồ là ngưỡng đóng cửa, không đảm bảo giá khớp.
- Không sửa backtesting.py, strategy_experiments.py, TCBS auth, 1 Giờ, Tuần,
  baseline tiến cứu, main hoặc cloud-dev. Không thêm Initial Stop/Profit Protection.
- Chạy kiểm thử offline bằng GitHub Actions. Thử HPG/MBB khung Ngày,
  kiểm tra nến cuối, đường Stop và backtesting; đối chiếu khung 1 Giờ/Tuần.
