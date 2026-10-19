"""Gemini 调用及结构化结果校验；此模块不保存或输出 API Key。"""

import json
import os
import re
import tomllib
from pathlib import Path


STYLE_NAMES = {
    "pain": "痛点营销型",
    "experience": "实战体验型",
    "promotion": "促销转化型",
}
SCRIPT_FIELDS = ("hook", "selling_points", "usage_scene", "call_to_action", "voiceover")
FIELD_NAMES = {
    "hook": "前三秒钩子",
    "selling_points": "产品核心卖点",
    "usage_scene": "实战使用场景",
    "call_to_action": "结尾购买引导",
    "voiceover": "完整口播文案",
}
FACT_CLAIM_PATTERN = re.compile(
    r"[¥￥]\s*\d+(?:\.\d+)?"
    r"|\d+(?:\.\d+)?\s*(?:元|折|[%％]|毫升|ml|mL|克|kg|公斤|小时)"
    r"|买[一1]送[一1]|满\s*\d+\s*减\s*\d+"
    r"|(?:官方|国家|权威)认证"
)


class InvalidAIResponse(ValueError):
    """模型返回了无法用于页面或 Excel 的内容。"""


def get_model_name() -> str:
    """环境变量优先，其次读取项目公开配置文件。"""
    from_environment = os.getenv("GEMINI_MODEL", "").strip()
    if from_environment:
        return from_environment
    config_path = Path(__file__).with_name("settings.toml")
    try:
        with config_path.open("rb") as config_file:
            model = tomllib.load(config_file).get("gemini_model", "")
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError("无法读取 settings.toml 中的 Gemini 模型配置。") from error
    if not isinstance(model, str) or not model.strip():
        raise ValueError("请在 settings.toml 中填写 gemini_model，或设置 GEMINI_MODEL 环境变量。")
    return model.strip()


def get_api_key(secrets=None) -> str:
    """读取环境变量或 Streamlit secrets，不在异常信息中放入密钥。"""
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        key = os.getenv(name, "").strip()
        if key:
            return key
    if secrets is not None:
        try:
            return str(secrets.get("GEMINI_API_KEY", "") or secrets.get("GOOGLE_API_KEY", "")).strip()
        except FileNotFoundError:
            return ""
    return ""


def _json_schema() -> dict:
    script_schema = {
        "type": "object",
        "properties": {field: {"type": "string"} for field in SCRIPT_FIELDS},
        "required": list(SCRIPT_FIELDS),
    }
    return {
        "type": "object",
        "properties": {style: script_schema for style in STYLE_NAMES},
        "required": list(STYLE_NAMES),
    }


def parse_ai_response(response_text: str | None) -> dict[str, dict[str, str]]:
    """严格检查三个风格和五项内容，避免残缺结果覆盖已编辑脚本。"""
    if not response_text:
        raise InvalidAIResponse("AI 未返回内容，请重试；已有脚本已保留。")
    try:
        data = json.loads(response_text)
    except (TypeError, json.JSONDecodeError) as error:
        raise InvalidAIResponse("AI 返回的内容不是有效 JSON，请重试；已有脚本已保留。") from error
    if not isinstance(data, dict):
        raise InvalidAIResponse("AI 返回的 JSON 顶层应为对象；已有脚本已保留。")
    unexpected_styles = set(data) - set(STYLE_NAMES)
    if unexpected_styles:
        raise InvalidAIResponse("AI 返回的脚本不止指定的三种风格；已有脚本已保留。")

    validated = {}
    for style_key, style_name in STYLE_NAMES.items():
        script = data.get(style_key)
        if not isinstance(script, dict):
            raise InvalidAIResponse(f"AI 结果缺少“{style_name}”脚本；已有脚本已保留。")
        if set(script) - set(SCRIPT_FIELDS):
            raise InvalidAIResponse(f"AI 结果中“{style_name}”包含预期之外的字段；已有脚本已保留。")
        for field in SCRIPT_FIELDS:
            if not isinstance(script.get(field), str) or not script[field].strip():
                raise InvalidAIResponse(
                    f"AI 结果中“{style_name}”的“{FIELD_NAMES[field]}”缺失或为空；已有脚本已保留。"
                )
        validated[style_key] = {field: script[field].strip() for field in SCRIPT_FIELDS}
    if len({script["voiceover"] for script in validated.values()}) != len(STYLE_NAMES):
        raise InvalidAIResponse("AI 返回的三条完整口播文案有重复，请重试；已有脚本已保留。")
    return validated


def check_unprovided_claims(scripts: dict[str, dict[str, str]], source_text: str) -> None:
    """拦截明显未提供的价格、折扣、数字参数和认证；人工仍需核对事实。"""
    supplied = re.sub(r"\s+", "", source_text).lower()
    for style_key, script in scripts.items():
        for field in SCRIPT_FIELDS:
            for match in FACT_CLAIM_PATTERN.finditer(script[field]):
                claim = re.sub(r"\s+", "", match.group()).lower()
                if claim not in supplied:
                    raise InvalidAIResponse(
                        f"AI 的“{STYLE_NAMES[style_key]}”疑似写入未提供的价格、优惠、数字参数或认证；"
                        "请核对产品信息后重新生成。已有脚本已保留。"
                    )


def voiceover_timing_note(voiceover: str, duration: int) -> str | None:
    """用宽松的字数范围提醒试读，不把字数当成实际口播时长。"""
    character_count = sum(char.isalnum() for char in voiceover)
    minimum, maximum = duration * 2, duration * 5
    if character_count < minimum:
        return f"完整口播约 {character_count} 字，可能短于 {duration} 秒；建议试读并补充内容。"
    if character_count > maximum:
        return f"完整口播约 {character_count} 字，可能超过 {duration} 秒；建议试读并精简内容。"
    return None


def describe_ai_error(error: Exception) -> str:
    """只用错误类型/状态码组织中文提示，避免把含密钥的异常原文放到页面。"""
    status = getattr(error, "code", None)
    if status == 401:
        return "Gemini 返回 401：密钥无效或已过期。请检查本机密钥配置；已有脚本已保留。"
    if status == 402:
        return "Gemini 返回 402：当前项目的账户额度或付款状态不满足调用条件。请在 Google AI Studio 检查；已有脚本已保留。"
    if status == 403:
        return "Gemini 返回 403：此密钥所属项目目前没有 API 访问权限。请在 Google AI Studio 检查项目状态和密钥权限；已有脚本已保留。"
    if status == 404:
        return "Gemini 返回 404：所选模型对当前项目不可用。请检查 settings.toml 中的模型名称；已有脚本已保留。"
    if status == 429:
        return "Gemini 返回 429：已达到调用速率或配额限制。请查看项目用量，稍后再试；已有脚本已保留。"
    if status in (500, 502, 503, 504):
        return "Gemini 服务暂时不可用，请稍后再试；已有脚本已保留。"
    error_types = {error_type.__name__ for error_type in type(error).__mro__}
    if error_types & {
        "TimeoutError", "ConnectionError", "TimeoutException", "NetworkError",
        "TransportError", "APIConnectionError",
    }:
        return "连接 Gemini 超时或网络中断。请检查网络后重试；已有脚本已保留。"
    return "Gemini 调用失败。请检查密钥、模型名称、网络连接和 API 额度；已有脚本已保留。"


def generate_ai_scripts(
    product: str,
    selling_points: str,
    audience: str,
    duration: int,
    api_key: str,
    model: str,
    *,
    client=None,
) -> dict[str, dict[str, str]]:
    """一次请求生成三种风格；client 参数仅用于离线模拟测试。"""
    if not api_key:
        raise ValueError("尚未配置 Gemini API Key。")
    if not model:
        raise ValueError("尚未配置 Gemini 模型名称。")

    if client is None:
        from google import genai

        client = genai.Client(api_key=api_key)

    instructions = (
        "你是中文短视频营销脚本写作者。请为抖音短视频写三条风格明显不同的文案："
        "痛点营销型、实战体验型、促销转化型。语言自然、口语化、通俗易懂。"
        "每条都要有前三秒钩子、产品核心卖点、真实可拍的使用场景、结尾购买引导，"
        "并给出能直接朗读的完整口播文案。口播长度应适合指定秒数。"
        f"完整口播请大致控制在 {duration * 2}～{duration * 5} 个中文字之间，最终以实际试读为准。"
        "只能使用用户提供的产品信息；不要编造参数、功效、价格、销量、用户评价或优惠活动。"
        "如果没有优惠信息，促销转化型只引导查看商品详情或当前实际价格，不得写虚构优惠。"
        "请按给定 JSON schema 返回结果，不要输出 Markdown。"
    )
    inputs = json.dumps(
        {
            "产品名称": product,
            "核心卖点": selling_points,
            "目标用户": audience,
            "视频时长（秒）": duration,
        },
        ensure_ascii=False,
    )
    response = client.models.generate_content(
        model=model,
        contents=f"请根据以下用户填写的信息创作：\n{inputs}",
        config={
            "system_instruction": instructions,
            "response_mime_type": "application/json",
            "response_json_schema": _json_schema(),
        },
    )
    scripts = parse_ai_response(response.text)
    check_unprovided_claims(scripts, "\n".join((product, selling_points, audience)))
    return scripts
