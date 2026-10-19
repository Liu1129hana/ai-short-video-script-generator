"""AI 模式的共享访问密码校验；不保存或输出明文密码。"""

import hashlib
import hmac


def get_app_password(secrets) -> str:
    """访问密码只从 Streamlit Secrets 读取；缺失时拒绝 AI 调用。"""
    try:
        password = secrets.get("APP_PASSWORD", "")
    except FileNotFoundError:
        return ""
    return password if isinstance(password, str) and password.strip() else ""


def password_tag(password: str) -> str:
    """只在服务器端会话中保存指纹，以便密码更改后旧会话失效。"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def is_ai_authenticated(session_tag: str | None, configured_password: str) -> bool:
    return bool(configured_password and session_tag) and hmac.compare_digest(
        session_tag, password_tag(configured_password)
    )


def check_password(submitted: str, configured_password: str) -> bool:
    return bool(submitted and configured_password) and hmac.compare_digest(
        submitted.encode("utf-8"), configured_password.encode("utf-8")
    )
