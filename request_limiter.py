"""公开网页的轻量级 AI 调用上限，使用 Python 自带的 SQLite。"""

import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


DAILY_LIMIT = 30
SESSION_DAILY_LIMIT = 5
DB_PATH = Path(tempfile.gettempdir()) / "ai-short-video-script-generator-limits.sqlite3"


class RateLimitError(ValueError):
    """拒绝超额调用，页面可直接显示此中文信息。"""


def reserve_ai_request(session_id: str, *, db_path: Path = DB_PATH, now: datetime | None = None) -> None:
    """在请求前原子计数；失败请求也计入，以防反复点击消耗额度。"""
    if not session_id:
        raise RateLimitError("无法确认页面会话，暂不能调用 AI。请刷新网页后再试。")
    current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    day = current.date().isoformat()
    try:
        with closing(sqlite3.connect(db_path, timeout=5)) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS ai_requests (day TEXT NOT NULL, session_id TEXT NOT NULL)"
                )
                connection.execute("DELETE FROM ai_requests WHERE day <> ?", (day,))
                total = connection.execute(
                    "SELECT COUNT(*) FROM ai_requests WHERE day = ?", (day,)
                ).fetchone()[0]
                if total >= DAILY_LIMIT:
                    raise RateLimitError("今天全站的 AI 调用次数已用完，请明天再试；已有脚本已保留。")
                session_total = connection.execute(
                    "SELECT COUNT(*) FROM ai_requests WHERE day = ? AND session_id = ?",
                    (day, session_id),
                ).fetchone()[0]
                if session_total >= SESSION_DAILY_LIMIT:
                    raise RateLimitError("当前页面今天的 AI 调用次数已用完；已有脚本已保留。")
                connection.execute(
                    "INSERT INTO ai_requests (day, session_id) VALUES (?, ?)", (day, session_id)
                )
    except sqlite3.Error as error:
        raise RateLimitError("无法检查 AI 调用次数，暂不能发起请求，请稍后再试；已有脚本已保留。") from error
