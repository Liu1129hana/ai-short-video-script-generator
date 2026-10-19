"""只替换指定脚本段落，保留用户对其他内容的编辑。"""

from excel_export import SECTION_PATTERN, VOICEOVER_PATTERN


FIELD_LABELS = {
    "hook": "开头钩子",
    "selling_points": "核心卖点",
    "call_to_action": "购买引导",
}


def _section_span(script: str, field: str) -> tuple[int, int, str]:
    label = FIELD_LABELS[field]
    section_end = (match.start() if (match := VOICEOVER_PATTERN.search(script)) else len(script))
    matches = list(SECTION_PATTERN.finditer(script, 0, section_end))
    targets = [(index, match) for index, match in enumerate(matches) if match.group(1) == label]
    if len(targets) != 1:
        raise ValueError(f"找不到唯一的“{label}”段落，请保留原有段落标签后重试；已有编辑已保留。")
    index, target = targets[0]
    end = matches[index + 1].start() if index + 1 < len(matches) else section_end
    raw = script[target.end():end]
    if not raw.strip():
        raise ValueError(f"“{label}”段落为空，请先填写内容；已有编辑已保留。")
    return target.end(), end, raw


def get_section(script: str, field: str) -> str:
    return _section_span(script, field)[2].strip()


def replace_section(script: str, field: str, replacement: str) -> tuple[str, bool]:
    """返回新脚本和口播是否同步更新；其他段落按原字符保留。"""
    if not replacement.strip():
        raise ValueError("AI 没有返回有效的优化文案；已有编辑已保留。")
    start, end, old_raw = _section_span(script, field)
    old_text = old_raw.strip()
    leading = old_raw[: len(old_raw) - len(old_raw.lstrip())]
    trailing = old_raw[len(old_raw.rstrip()):]
    updated = script[:start] + leading + replacement.strip() + trailing + script[end:]
    voiceover_match = VOICEOVER_PATTERN.search(updated)
    if voiceover_match:
        prefix = updated[:voiceover_match.end()]
        voiceover = updated[voiceover_match.end():]
        if voiceover.count(old_text) == 1:
            return prefix + voiceover.replace(old_text, replacement.strip(), 1), True
    return updated, False
