"""AI 短视频营销脚本生成器的本地示例页面。"""

import re
import time
import uuid
from datetime import date
from threading import Condition

import streamlit as st

from access_control import check_password, get_app_password, is_ai_authenticated, password_tag
from excel_export import export_filename, get_voiceover, make_excel_bytes, missing_sections
from deepseek_service import (
    InvalidAIResponse,
    describe_ai_error,
    generate_ai_scripts,
    get_api_key,
    get_model_name,
    voiceover_timing_note,
)
from request_limiter import DAILY_LIMIT, SESSION_DAILY_LIMIT, reserve_ai_request


PAGE_TITLE = "AI短视频营销脚本生成器"
AI_REQUEST_COOLDOWN_SECONDS = 8
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60
VIDEO_DURATIONS = (15, 20, 30, 60)
STYLES = (
    ("pain", "痛点营销型"),
    ("experience", "实战体验型"),
    ("promotion", "促销转化型"),
)
TIME_SEGMENTS = {
    15: ((0, 3), (3, 7), (7, 12), (12, 15)),
    20: ((0, 3), (3, 9), (9, 16), (16, 20)),
    30: ((0, 3), (3, 12), (12, 24), (24, 30)),
    60: ((0, 3), (3, 23), (23, 48), (48, 60)),
}


class ExportState:
    """让下载等待编辑框的最新状态，避免拿到上一次渲染的文件。"""

    def __init__(self) -> None:
        self.condition = Condition()
        self.revision = 0
        self.snapshot = None

    def update(self, snapshot: dict) -> int:
        with self.condition:
            self.revision += 1
            self.snapshot = snapshot
            self.condition.notify_all()
            return self.revision

    def after(self, revision: int) -> dict:
        with self.condition:
            if not self.condition.wait_for(lambda: self.revision > revision, timeout=15):
                raise TimeoutError("编辑内容尚未同步，未生成 Excel，请重试下载。")
            return self.snapshot


def make_example_scripts(product: str, selling_points: str, audience: str, duration: int) -> dict[str, str]:
    """根据输入填充三种本地示例模板，不调用 AI。"""
    points = [point.strip() for point in re.split(r"[，,、；;\n]+", selling_points) if point.strip()]
    point_text = "、".join(points)
    segments = TIME_SEGMENTS[duration]

    def line(index: int, label: str, content: str) -> str:
        start, end = segments[index]
        return f"【{start}—{end} 秒｜{label}】{content}"

    return {
        "pain": "\n".join(
            (
                line(0, "开头钩子", f"买{product}前，你最担心哪一点？"),
                line(1, "核心卖点", f"先看这款{product}：{point_text}。"),
                line(2, "使用场景", f"让{audience}在日常场景中用一次{product}，展示实际操作。"),
                line(3, "购买引导", "想了解更多？进入商品页核对规格和价格，再决定是否购买。"),
            )
        ),
        "experience": "\n".join(
            (
                line(0, "开头钩子", f"别只看介绍，{product}上手怎么样？"),
                line(1, "核心卖点", f"镜头展示这些重点：{point_text}。"),
                line(2, "使用场景", f"请{audience}按真实流程使用{product}，拍下关键步骤。"),
                line(3, "购买引导", "想亲自试试？到商品页查看详情，选择适合自己的款式。"),
            )
        ),
        "promotion": "\n".join(
            (
                line(0, "开头钩子", f"准备入手{product}？先看这几个重点！"),
                line(1, "核心卖点", f"这款{product}的主要看点：{point_text}。"),
                line(2, "使用场景", f"展示{audience}从开始到完成一次{product}使用的过程。"),
                line(3, "购买引导", "现在进入商品页，核对当前优惠、规格和价格；合适再下单。"),
            )
        ),
    }


def format_ai_scripts(result: dict[str, dict[str, str]], duration: int) -> dict[str, str]:
    """把结构化 AI 结果放进原有的可编辑脚本框。"""
    segments = TIME_SEGMENTS[duration]
    labels = (
        ("hook", "开头钩子"),
        ("selling_points", "核心卖点"),
        ("usage_scene", "使用场景"),
        ("call_to_action", "购买引导"),
    )
    scripts = {}
    for style_key, _ in STYLES:
        lines = []
        for index, (field, label) in enumerate(labels):
            start, end = segments[index]
            lines.append(f"【{start}—{end} 秒｜{label}】{result[style_key][field]}")
        lines.append(f"【完整口播文案】{result[style_key]['voiceover']}")
        scripts[style_key] = "\n".join(lines)
    return scripts


def unlock_ai() -> None:
    """按钮回调在组件重绘前运行，验证后立即清空输入的密码。"""
    submitted = st.session_state.get("app_password_input", "")
    st.session_state["app_password_input"] = ""
    configured_password = get_app_password(st.secrets)
    now = time.monotonic()
    if now < st.session_state.get("login_locked_until", 0):
        st.session_state["login_message"] = "密码尝试过于频繁，请稍后再试。"
    elif check_password(submitted, configured_password):
        st.session_state["ai_auth_tag"] = password_tag(configured_password)
        st.session_state["login_failures"] = 0
        st.session_state.pop("login_message", None)
    else:
        st.session_state.pop("ai_auth_tag", None)
        failures = st.session_state.get("login_failures", 0) + 1
        st.session_state["login_failures"] = failures
        if failures >= MAX_LOGIN_ATTEMPTS:
            st.session_state["login_locked_until"] = now + LOGIN_LOCKOUT_SECONDS
            st.session_state["login_message"] = "密码尝试过于频繁，请 15 分钟后再试。"
        else:
            st.session_state["login_message"] = "访问密码不正确。"


def lock_ai() -> None:
    st.session_state.pop("ai_auth_tag", None)
    st.session_state.pop("login_message", None)


st.set_page_config(page_title=PAGE_TITLE, page_icon="🎬", layout="wide")
st.markdown(
    """
    <style>
    header[data-testid="stHeader"] { display: none; }
    .block-container { max-width: 1280px; padding-top: 2rem; }
    h1 { color: #17315b; letter-spacing: -0.03em; }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: #ffffff;
        border-radius: 16px;
    }
    @media (max-width: 850px) {
        [data-testid="stHorizontalBlock"] { flex-direction: column !important; }
        [data-testid="stColumn"] { width: 100% !important; flex: 1 1 100% !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(PAGE_TITLE)
st.caption("填写产品信息，选择生成模式，查看并修改三种风格的短视频营销脚本。")

input_column, result_column = st.columns([1, 1.45], gap="large")

with input_column:
    with st.container(border=True):
        st.subheader("填写产品信息")
        generation_mode = st.radio(
            "生成模式",
            ("示例模式", "AI生成模式"),
            horizontal=True,
            key="generation_mode",
            help="示例模式免费在本地运行；AI生成模式需要 DeepSeek API Key，并可能产生 API 用量和费用。",
        )
        if generation_mode == "示例模式":
            st.info("示例模式使用本地固定模板，不调用 AI API。")
        else:
            configured_password = get_app_password(st.secrets)
            ai_authenticated = is_ai_authenticated(
                st.session_state.get("ai_auth_tag"), configured_password
            )
            if not configured_password:
                st.warning("管理员尚未在 Streamlit Secrets 中配置 APP_PASSWORD，AI 模式暂不可用。")
            elif not ai_authenticated:
                st.info("AI 生成需要访问密码；示例模式可以直接使用。")
                st.text_input("访问密码", type="password", key="app_password_input")
                st.button("解锁 AI 生成", key="unlock_ai", on_click=unlock_ai)
                if st.session_state.get("login_message"):
                    st.error(st.session_state["login_message"])
            else:
                st.success("AI 生成已解锁（仅限当前页面会话）。")
                st.button("退出 AI 登录", key="lock_ai", on_click=lock_ai)
                if get_api_key(st.secrets):
                    st.info("已检测到 DeepSeek API Key。点击生成按钮后会向 DeepSeek 发送填写的产品信息。")
                else:
                    st.warning("尚未读取到 DeepSeek API Key。请在 Streamlit Secrets 或环境变量中配置 DEEPSEEK_API_KEY；示例模式仍可使用。")
            st.caption(f"为控制公开网页用量：全站每天最多 {DAILY_LIMIT} 次、每个页面会话每天最多 {SESSION_DAILY_LIMIT} 次 AI 请求。失败尝试也计入；服务重启后计数可能重置。")
            if st.session_state.get("last_ai_error"):
                st.error(f"上次 AI 生成未成功：{st.session_state['last_ai_error']}")
        product_name = st.text_input("产品名称", placeholder="例如：便携咖啡杯", key="product_name")
        selling_points = st.text_area(
            "核心卖点",
            placeholder="例如：防漏、轻便、容易清洗；可用逗号或换行分隔",
            height=130,
            key="selling_points",
        )
        target_audience = st.text_input(
            "目标用户", placeholder="例如：每天通勤的上班族", key="target_audience"
        )
        video_duration = st.selectbox(
            "视频时长", VIDEO_DURATIONS, format_func=lambda seconds: f"{seconds}秒", index=2, key="video_duration"
        )
        generate_clicked = st.button(
            "生成营销脚本",
            key="generate_scripts",
            type="primary",
            use_container_width=True,
            disabled=generation_mode == "AI生成模式" and not is_ai_authenticated(
                st.session_state.get("ai_auth_tag"), get_app_password(st.secrets)
            ),
        )
        st.caption("再次点击会按当前输入重新生成三条脚本，并覆盖之前的编辑；调用失败则保留原文。AI 模式对相同输入设置短暂间隔，避免连续点击重复调用。")

    if generate_clicked:
        missing = []
        if not product_name.strip():
            missing.append("产品名称")
        if not any(part.strip() for part in re.split(r"[，,、；;\n]+", selling_points)):
            missing.append("核心卖点")
        if not target_audience.strip():
            missing.append("目标用户")

        if missing:
            st.warning(f"请先填写：{'、'.join(missing)}。")
        else:
            scripts = None
            if generation_mode == "示例模式":
                scripts = make_example_scripts(
                    product_name.strip(), selling_points.strip(), target_audience.strip(), video_duration
                )
            elif not is_ai_authenticated(
                st.session_state.get("ai_auth_tag"), get_app_password(st.secrets)
            ):
                message = "请先输入正确的访问密码，才能使用 AI 生成；已有脚本不会清空。"
                st.session_state["last_ai_error"] = message
                st.error(message)
            elif not (api_key := get_api_key(st.secrets)):
                message = "尚未配置 DeepSeek API Key。请先配置，或切回示例模式。已有脚本不会清空。"
                st.session_state["last_ai_error"] = message
                st.error(message)
            else:
                try:
                    model_name = get_model_name()
                    request_signature = (
                        product_name.strip(),
                        selling_points.strip(),
                        target_audience.strip(),
                        video_duration,
                        model_name,
                    )
                    previous_request = st.session_state.get("last_ai_request")
                    now = time.monotonic()
                    if (
                        previous_request
                        and previous_request[0] == request_signature
                        and now - previous_request[1] < AI_REQUEST_COOLDOWN_SECONDS
                    ):
                        st.warning("相同内容刚发起过 AI 请求。为避免重复调用，请稍等几秒再试；已有脚本已保留。")
                    else:
                        st.session_state["last_ai_request"] = (request_signature, now)
                        try:
                            if "ai_session_id" not in st.session_state:
                                st.session_state["ai_session_id"] = uuid.uuid4().hex
                            reserve_ai_request(st.session_state["ai_session_id"])
                            with st.spinner("DeepSeek 正在生成三条脚本，请稍候……"):
                                result = generate_ai_scripts(
                                    product_name.strip(),
                                    selling_points.strip(),
                                    target_audience.strip(),
                                    video_duration,
                                    api_key,
                                    model_name,
                                )
                        finally:
                            st.session_state["last_ai_request"] = (request_signature, time.monotonic())
                        scripts = format_ai_scripts(result, video_duration)
                except (InvalidAIResponse, ValueError) as error:
                    st.session_state["last_ai_error"] = str(error)
                    st.error(str(error))
                except Exception as error:
                    message = describe_ai_error(error)
                    st.session_state["last_ai_error"] = message
                    st.error(message)

            if scripts is not None:
                st.session_state.pop("last_ai_error", None)
                for style_key, script in scripts.items():
                    st.session_state[f"script_{style_key}"] = script
                st.session_state["last_generated_inputs"] = (
                    product_name,
                    selling_points,
                    target_audience,
                    video_duration,
                )
                st.session_state["last_generated_mode"] = generation_mode
                st.session_state["has_scripts"] = True

with result_column:
    st.subheader("脚本结果")
    if not st.session_state.get("has_scripts", False):
        with st.container(border=True):
            st.markdown("填写左侧信息并点击 **生成营销脚本**，这里会出现三条可编辑的脚本。")
            st.download_button(
                "下载Excel脚本",
                data=b"",
                file_name="营销脚本.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                disabled=True,
                width="stretch",
            )
            st.caption("生成三条脚本后才能下载 Excel。如果 AI 模式暂时无法生成，可切换左侧的“示例模式”继续体验导出。")
    else:
        current_inputs = (product_name, selling_points, target_audience, video_duration)
        if current_inputs != st.session_state["last_generated_inputs"]:
            st.info("输入信息已改变，下面的脚本和修改仍会保留。需要更新示例时，请再次点击“生成营销脚本”。")
        last_mode = st.session_state.get("last_generated_mode", "示例模式")
        st.caption(
            f"当前显示：{last_mode}生成的脚本。分段时长仅供参考，发布前请按实际口播速度调整。"
        )
        if last_mode == "AI生成模式":
            st.caption("系统会拦截明显缺乏依据的价格、折扣、数字参数和认证表述；其他产品事实仍需人工核对。")
        edited_scripts = {}
        for style_key, style_name in STYLES:
            with st.container(border=True):
                st.markdown(f"#### {style_name} · {'AI脚本' if last_mode == 'AI生成模式' else '示例脚本'}")
                edited_scripts[style_key] = st.text_area(
                    f"编辑{style_name}脚本",
                    key=f"script_{style_key}",
                    height=200,
                    help="直接修改文字即可。修改会在当前页面会话中保留。",
                )
                if last_mode == "AI生成模式" and not missing_sections(edited_scripts[style_key]):
                    timing_note = voiceover_timing_note(
                        get_voiceover(edited_scripts[style_key]),
                        st.session_state["last_generated_inputs"][3],
                    )
                    if timing_note:
                        st.caption(f"⏱️ {timing_note}")

        st.caption("下载时会按【时间｜段落名称】拆分四段；如有【完整口播文案】，也会按编辑后的原文导出。修改分段后，请同步核对口播文案，并保留标签。")
        invalid_styles = [
            style_name
            for style_key, style_name in STYLES
            if missing_sections(edited_scripts[style_key])
        ]
        missing_product_info = not (
            product_name.strip() and selling_points.strip() and target_audience.strip()
        )
        can_download = not invalid_styles and not missing_product_info
        if invalid_styles:
            st.warning(f"请检查{'、'.join(invalid_styles)}：必要内容或段落标签不完整，暂时不能下载。")
        elif missing_product_info:
            st.warning("请先补全产品名称、核心卖点和目标用户，再下载 Excel。")

        if "excel_export_state" not in st.session_state:
            st.session_state["excel_export_state"] = ExportState()
        export_state = st.session_state["excel_export_state"]
        export_date = date.today()
        rendered_product = product_name.strip()
        rendered_revision = export_state.update(
            {
                "product": rendered_product,
                "selling_points": selling_points.strip(),
                "audience": target_audience.strip(),
                "duration": video_duration,
                "scripts": edited_scripts.copy(),
                "export_date": export_date,
                "can_download": can_download,
            }
        )

        def current_excel_bytes() -> bytes:
            latest = export_state.after(rendered_revision)
            if not latest["can_download"] or latest["product"] != rendered_product:
                raise ValueError("页面信息已变化，请确认后重新点击下载。")
            return make_excel_bytes(
                latest["product"],
                latest["selling_points"],
                latest["audience"],
                latest["duration"],
                latest["scripts"],
                latest["export_date"],
            )

        st.download_button(
            "下载Excel脚本",
            data=current_excel_bytes,
            file_name=export_filename(product_name, export_date),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=not can_download,
            on_click="rerun",
            width="stretch",
        )
