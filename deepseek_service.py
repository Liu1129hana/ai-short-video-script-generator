"""DeepSeek 调用及结构化结果校验；此模块不保存或输出 API Key。"""

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
    from_environment = os.getenv("DEEPSEEK_MODEL", "").strip()
    if from_environment:
        return from_environment
    config_path = Path(__file__).with_name("settings.toml")
    try:
        with config_path.open("rb") as config_file:
            model = tomllib.load(config_file).get("deepseek_model", "")
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError("无法读取 settings.toml 中的 DeepSeek 模型配置。") from error
    if not isinstance(model, str) or not model.strip():
        raise ValueError("请在 settings.toml 中填写 deepseek_model，或设置 DEEPSEEK_MODEL 环境变量。")
    return model.strip()


def get_api_key(secrets=None) -> str:
    """读取环境变量或 Streamlit secrets，不在异常信息中放入密钥。"""
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    if secrets is not None:
        try:
            return str(secrets.get("DEEPSEEK_API_KEY", "")).strip()
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
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None) or getattr(error, "status_code", None) or getattr(error, "code", None)
    if status == 400 or status == 422:
        return f"DeepSeek 返回 {status}：请求格式或参数不正确，请检查模型配置；已有脚本已保留。"
    if status == 401:
        return "DeepSeek 返回 401：API Key 无效或已过期，请检查密钥配置；已有脚本已保留。"
    if status == 402:
        return "DeepSeek 返回 402：账户余额不足，请在 DeepSeek 开放平台检查；已有脚本已保留。"
    if status == 403:
        return "DeepSeek 返回 403：此密钥没有访问权限，请在 DeepSeek 开放平台检查；已有脚本已保留。"
    if status == 404:
        return "DeepSeek 返回 404：所选模型不可用，请检查 settings.toml 中的模型名称；已有脚本已保留。"
    if status == 429:
        return "DeepSeek 返回 429：调用过于频繁或达到并发限制，请稍后再试；已有脚本已保留。"
    if status in (500, 502, 503, 504):
        return "DeepSeek 服务暂时不可用，请稍后再试；已有脚本已保留。"
    error_types = {error_type.__name__ for error_type in type(error).__mro__}
    if error_types & {
        "TimeoutError", "ConnectionError", "TimeoutException", "NetworkError",
        "TransportError", "APIConnectionError", "APITimeoutError", "ConnectError", "ReadTimeout",
    }:
        return "连接 DeepSeek 超时或网络中断，请检查网络后重试；已有脚本已保留。"
    return "DeepSeek 调用失败，请检查密钥、模型名称、网络连接和账户余额；已有脚本已保留。"


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
        raise ValueError("尚未配置 DeepSeek API Key。")
    if not model:
        raise ValueError("尚未配置 DeepSeek 模型名称。")

    if client is None:
        import httpx

        client = httpx

    instructions = (
        "你是中文短视频营销脚本写作者。请为抖音短视频写三条风格明显不同的文案："
        "痛点营销型、实战体验型、促销转化型。语言自然、口语化、通俗易懂。"
        "每条都要有前三秒钩子、产品核心卖点、真实可拍的使用场景、结尾购买引导，"
        "并给出能直接朗读的完整口播文案。口播长度应适合指定秒数。"
        f"完整口播请大致控制在 {duration * 2}～{duration * 5} 个中文字之间，最终以实际试读为准。"
        "只能使用用户提供的产品信息；不要编造参数、功效、价格、销量、用户评价或优惠活动。"
        "如果没有优惠信息，促销转化型只引导查看商品详情或当前实际价格，不得写虚构优惠。"
        "只返回 JSON 对象，不要输出 Markdown。严格按照以下结构和字段名填写，所有字段均为非空字符串："
        + json.dumps(_json_schema(), ensure_ascii=False)
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
    response = client.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": f"请根据以下用户填写的信息创作 JSON：\n{inputs}"},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 2500,
            "stream": False,
        },
        timeout=60,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as error:
        raise InvalidAIResponse("DeepSeek 返回的接口数据不是有效 JSON；已有脚本已保留。") from error
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise InvalidAIResponse("DeepSeek 返回的接口数据缺少脚本内容；已有脚本已保留。")
    choice = choices[0]
    if choice.get("finish_reason") == "length":
        raise InvalidAIResponse("AI 返回内容被截断，请重试；已有脚本已保留。")
    if choice.get("finish_reason") != "stop":
        raise InvalidAIResponse("AI 未完成脚本生成，请重试；已有脚本已保留。")
    message = choice.get("message")
    scripts = parse_ai_response(message.get("content") if isinstance(message, dict) else None)
    check_unprovided_claims(scripts, "\n".join((product, selling_points, audience)))
    return scripts
