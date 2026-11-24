# Phân loại chiến lược Stock Bot V3

Nhánh research-v3 tách nghiên cứu mới khỏi cloud-dev đã khóa đối chứng.

- SMA50/SMA200: ưu tiên nghiên cứu, chưa phải tín hiệu mặc định.
- V1: đối chứng; tín hiệu vận hành hiện tại không đổi.
- ADX + DI + MACD: nghiên cứu bổ trợ.
- V2 và V2.1: lưu trữ; không chạy mặc định trên báo cáo nghiên cứu khung Ngày, vẫn truy xuất được.
- Tất cả 5 chiến lược (đối chứng lịch sử): lựa chọn rõ ràng để tái lập báo cáo cũ.
- Không thay đổi TCBS, công thức chỉ báo, thuật toán khớp lệnh, chi phí, khung 1 Giờ hoặc cảnh báo Tuần.
- Không dùng kết quả nhánh này thay cho nhật ký tiến cứu của baseline cố định; tiếp tục thu thập baseline trên cloud-dev đúng commit/cấu hình.

Kiểm thử: python -m unittest discover -s tests -p 'test_*.py' -v
