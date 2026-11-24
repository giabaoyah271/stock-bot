"""Research strategy selection; never changes any trading rule."""
from multi_backtest_core import STRATEGY_NAMES

ACTIVE = STRATEGY_NAMES[1:2]
BENCHMARK = STRATEGY_NAMES[:1]
SUPPORTING = STRATEGY_NAMES[2:3]
ARCHIVED = STRATEGY_NAMES[3:]
RESEARCH = STRATEGY_NAMES[:3]
DEFAULT_GROUP = "Nhóm nghiên cứu chính (3 chiến lược)"
BASELINE_GROUP = "Tất cả 5 chiến lược (đối chứng lịch sử)"
GROUP_CHOICES = (DEFAULT_GROUP, BASELINE_GROUP)
CHOICES = GROUP_CHOICES + RESEARCH + ARCHIVED
ARCHIVE_LABEL = "Bật chiến lược lưu trữ V2/V2.1 (nghiên cứu lịch sử)"
RESEARCH_NOTE = (
    "SMA50/SMA200: ưu tiên nghiên cứu; V1: đối chứng; ADX + DI + MACD: bổ trợ. "
    "V2/V2.1 đã lưu trữ, không chạy mặc định. Không chiến lược nào được xác nhận sinh lời bền vững."
)

def resolve_strategies(choice):
    if choice == DEFAULT_GROUP:
        return RESEARCH
    if choice == BASELINE_GROUP:
        return STRATEGY_NAMES
    if choice in STRATEGY_NAMES:
        return (choice,)
    raise ValueError("Lựa chọn chiến lược không hợp lệ")
