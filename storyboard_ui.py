"""独立的 V1.3 分镜区：每种脚本/制作模式单独保留草稿。"""

from copy import deepcopy
import time
import uuid

import streamlit as st

from access_control import get_app_password, is_ai_authenticated
from deepseek_service import InvalidAIResponse, describe_ai_error, get_api_key, get_model_name, voiceover_timing_note
from excel_export import STYLE_NAMES, export_filename, get_voiceover, missing_sections
from request_limiter import RateLimitError, reserve_ai_request
from storyboard import CHARACTER_RULE, MODES, PRODUCT_RULE, fields_for, generate_storyboard, make_example_storyboard, normalized, validate_shots
from storyboard_export import make_storyboard_excel


def save_shot(board_key, index, field, widget_key):
    st.session_state["storyboards"][board_key]["shots"][index][field] = st.session_state[widget_key]


def generate_current_storyboard(example_only=False):
    state = st.session_state
    style, mode = state["storyboard_style"], state["storyboard_mode"]
    board_key = f"{style}:{mode}"
    try:
        scripts = {key: state.get(f"script_{key}", "") for key in STYLE_NAMES}
        if any(missing_sections(script) for script in scripts.values()):
            raise InvalidAIResponse("请补全三条脚本的必要段落和标签，以便保留完整的 Excel 导出。")
        inputs = state["last_generated_inputs"]
        product, points, audience, duration = inputs
        reference, character = state["storyboard_reference"].strip(), state["storyboard_character"].strip()
        generation_mode = state["generation_mode"]
        if len(scripts[style]) > 16000 or len(reference) > 4000 or len(character) > 2000:
            raise InvalidAIResponse("脚本或参考资料过长，请精简后重试。")
        if example_only or generation_mode == "示例模式":
            shots = make_example_storyboard(scripts[style], duration, mode, reference, character)
        else:
            if not is_ai_authenticated(state.get("ai_auth_tag"), get_app_password(st.secrets)):
                raise InvalidAIResponse("请先解锁 AI 生成；已有分镜已保留。")
            api_key = get_api_key(st.secrets)
            if not api_key:
                raise InvalidAIResponse("尚未配置 DeepSeek API Key；已有分镜已保留。")
            now = time.monotonic()
            if now - state.get("last_storyboard_time", -8) < 8:
                raise InvalidAIResponse("刚生成过分镜，请稍等几秒再试；已有分镜已保留。")
            model = get_model_name()
            if "ai_session_id" not in state:
                state["ai_session_id"] = uuid.uuid4().hex
            reserve_ai_request(state["ai_session_id"])
            state["last_storyboard_time"] = now
            try:
                with st.spinner("DeepSeek 正在设计分镜，请稍候……"):
                    shots = generate_storyboard(product, points, audience, duration, scripts[style], mode,
                                                reference, character, api_key, model)
            finally:
                state["last_storyboard_time"] = time.monotonic()
        # 只在全部完成后替换选定草稿；失败不改动任何已编辑内容。
        state.setdefault("storyboards", {})[board_key] = {
            "id": uuid.uuid4().hex, "style": style, "mode": mode, "inputs": inputs,
            "scripts": scripts, "reference": reference, "character": character,
            "shots": shots, "generation_mode": "本地示例（基于当前脚本）" if example_only else generation_mode,
        }
        state["storyboard_status"] = (board_key, "success", "分镜已生成，可逐镜编辑并导出。")
    except (InvalidAIResponse, RateLimitError) as error:
        state["storyboard_status"] = (board_key, "error", str(error))
    except Exception as error:
        state["storyboard_status"] = (board_key, "error", describe_ai_error(error) + "已有分镜已保留。")


def render_storyboards(export_state_class):
    if not st.session_state.get("has_scripts"):
        return
    st.divider()
    st.subheader("视频分镜 · V1.3")
    st.caption("选择一条已编辑脚本，生成真人实拍方案或 AI 视频制作提示词。这里只生成制作方案，不生成视频文件。")
    left, right = st.columns(2)
    with left:
        style = st.selectbox("选择分镜脚本", list(STYLE_NAMES), format_func=STYLE_NAMES.get, key="storyboard_style")
        reference = st.text_area("已确认产品资料（选填）", key="storyboard_reference", max_chars=4000,
                                 help="填写已核对的外观、颜色、结构、参数或参考图说明。链接仅作文字参考，不会自动读取网页或图片。")
    with right:
        mode = st.radio("制作模式", MODES, horizontal=True, key="storyboard_mode")
        character = st.text_area("人物设定与参考说明（选填）", key="storyboard_character", max_chars=2000,
                                 help="例如同一双手、固定服装、握持方式；未提供时优先使用不露脸手部镜头。")
    board_key = f"{style}:{mode}"
    use_ai = st.session_state["generation_mode"] == "AI生成模式"
    can_generate = not use_ai or is_ai_authenticated(st.session_state.get("ai_auth_tag"), get_app_password(st.secrets))
    st.button("AI生成视频分镜" if use_ai else "生成示例分镜", key="generate_storyboard", type="primary",
              disabled=not can_generate, on_click=generate_current_storyboard)
    if use_ai:
        st.button("使用示例分镜（不调用 AI）", key="example_storyboard_fallback",
                  on_click=generate_current_storyboard, args=(True,))
    st.caption("分镜使用原脚本对应的产品信息与时长。重新生成只覆盖当前脚本、当前制作模式的分镜；切换模式会保留草稿。"
               + ("AI 分镜每次计入原有每日用量，失败也计数。" if use_ai else "当前为本地示例，不调用 AI。"))
    status = st.session_state.get("storyboard_status")
    if status and status[0] == board_key:
        (st.success if status[1] == "success" else st.error)(status[2])
    record = st.session_state.get("storyboards", {}).get(board_key)
    if not record:
        return
    product, points, audience, duration = record["inputs"]
    st.markdown(f"**当前分镜：{STYLE_NAMES[style]} · {mode} · {duration}秒 · {record['generation_mode']}**")
    current_inputs = tuple(st.session_state[key] for key in ("product_name", "selling_points", "target_audience", "video_duration"))
    if (record["scripts"][style] != st.session_state[f"script_{style}"] or tuple(record["inputs"]) != current_inputs
            or record["reference"] != reference.strip() or record["character"] != character.strip()):
        st.warning("脚本、产品信息或参考设定已变化。当前分镜仍保留原来的内容，导出会附带生成时的资料和脚本；如需同步，请重新生成。")
    if mode == MODES[1]:
        st.info(CHARACTER_RULE + PRODUCT_RULE + "提示词不能保证模型准确还原产品，成片需逐镜复核。")
    elapsed = 0
    for index, shot in enumerate(record["shots"]):
        with st.expander(f"镜头 {index + 1} · {elapsed}–{elapsed + shot['duration']} 秒", expanded=index == 0):
            for field, label in fields_for(mode).items():
                widget_key = f"shot_{record['id']}_{index}_{field}"
                kwargs = dict(key=widget_key, on_change=save_shot, args=(board_key, index, field, widget_key))
                if field == "duration":
                    st.number_input(label, min_value=1, max_value=duration, step=1, value=shot[field], **kwargs)
                else:
                    st.text_area(label, value=shot[field], height=85, max_chars=4000, **kwargs)
            note = voiceover_timing_note(shot["dialogue"], shot["duration"]) if shot["dialogue"] else None
            if note:
                st.caption(note)
        elapsed += shot["duration"]
    st.caption(f"镜头合计 {elapsed} 秒 / 目标 {duration} 秒。编辑在当前会话内保留；刷新或关闭页面可能丢失，请及时下载。")
    if normalized("".join(shot["dialogue"] for shot in record["shots"])) != normalized(get_voiceover(record["scripts"][style])):
        st.info("分镜台词已手动修改，导出保留这些修改；原脚本快照不变，请核对两者。")
    valid = True
    try:
        validate_shots(record["shots"], mode, duration)
    except InvalidAIResponse as error:
        valid = False
        st.warning(str(error))
    export_key = "storyboard_export_state"
    if export_key not in st.session_state:
        st.session_state[export_key] = export_state_class()
    export_state = st.session_state[export_key]
    revision = export_state.update({"record": deepcopy(record), "valid": valid})
    rendered_id = record["id"]

    def download_latest():
        latest = export_state.after(revision)
        if not latest["valid"] or latest["record"]["id"] != rendered_id:
            raise ValueError("分镜已切换或内容尚未补全，请确认后重新下载。")
        return make_storyboard_excel(latest["record"])

    st.download_button("下载Excel制作方案", data=download_latest, key=f"download_storyboard_{rendered_id}",
                       file_name=export_filename(product).replace("营销脚本", f"{STYLE_NAMES[style]}_{mode}_制作方案"),
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       disabled=not valid, on_click="rerun")
