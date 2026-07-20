from datetime import datetime
from zoneinfo import ZoneInfo


def now_almaty_iso(timezone: str = "Asia/Almaty") -> str:
    """Текущее время в ISO 8601 с указанным часовым поясом."""
    return datetime.now(ZoneInfo(timezone)).isoformat()
