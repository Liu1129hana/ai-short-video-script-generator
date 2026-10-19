"""V1.2 离线验收：模拟 DeepSeek 响应，不使用真实密钥或计费接口。"""

import json
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from deepseek_service import (
    InvalidAIResponse,
    fit_scripts_to_duration,
    optimize_script_section,
    spoken_length,
)
from excel_export import get_voiceover, make_excel_bytes, parse_sections
from script_editing import replace_section
from test_quality import sample_result


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps(self.data, ensure_ascii=False),
        }}]}


class FakeClient:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.data)


class V12Tests(unittest.TestCase):
    def test_same_product_three_distinct_styles_and_short_voiceovers(self):
        sample = sample_result()
        sample["pain"]["hook"] = "通勤路上咖啡洒进包里，真会耽误一天的好心情吗？"
        sample["experience"]["usage_scene"] *= 15
        for duration, segments in (
            (15, (3, 4, 5, 3)), (20, (3, 6, 7, 4)),
            (30, (3, 9, 12, 6)), (60, (3, 20, 25, 12)),
        ):
            with self.subTest(duration=duration):
                fitted = fit_scripts_to_duration(sample, duration, segments)
                self.assertEqual(len({tuple(item[field] for field in (
                    "hook", "selling_points", "usage_scene", "call_to_action"
                )) for item in fitted.values()}), 3)
                for script in fitted.values():
                    self.assertLessEqual(spoken_length(script["hook"]), 12)
                    self.assertLessEqual(spoken_length(script["voiceover"]), duration * 4)
                    self.assertEqual(script["voiceover"], "".join(script[field] for field in (
                        "hook", "selling_points", "usage_scene", "call_to_action"
                    )))

    def test_local_api_only_requests_one_replacement_and_rejects_fabricated_price(self):
        client = FakeClient({"replacement": "咖啡杯放包里，先看防漏。"})
        result = optimize_script_section(
            "便携咖啡杯", "防漏、轻便、容易清洗", "通勤上班族", 30,
            "pain", "hook", "用户已编辑完整脚本", "原来的开头", "测试密钥", "test-model",
            segment_seconds=3, client=client,
        )
        self.assertLessEqual(spoken_length(result), 12)
        self.assertEqual(len(client.calls), 1)
        request = client.calls[0][1]["json"]
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertIn("用户已编辑完整脚本", request["messages"][1]["content"])
        self.assertIn("只优化用户指定的一段", request["messages"][0]["content"])
        with self.assertRaises(InvalidAIResponse):
            optimize_script_section(
                "便携咖啡杯", "防漏", "通勤上班族", 30, "promotion", "call_to_action",
                "旧脚本", "去看看商品页", "测试密钥", "test-model", segment_seconds=6,
                client=FakeClient({"replacement": "今天只要9.9元，立即下单。"}),
            )

    def test_replace_section_preserves_manual_edits_and_excel_uses_new_text(self):
        scripts = sample_result()
        original = (
            "【0—3 秒｜开头钩子】原钩子。\n"
            "【3—12 秒｜核心卖点】我手写的卖点，不要覆盖。\n"
            "【12—24 秒｜使用场景】我手写的场景。\n"
            "【24—30 秒｜购买引导】我手写的引导。\n"
            "【完整口播文案】原钩子。我手写的卖点，不要覆盖。我手写的场景。我手写的引导。"
        )
        updated, synced = replace_section(original, "hook", "新的三秒钩子。")
        self.assertTrue(synced)
        self.assertEqual(updated, original.replace("原钩子。", "新的三秒钩子。"))
        unchanged, synced = replace_section(
            original.replace("【完整口播文案】原钩子。", "【完整口播文案】用户另写的口播。"),
            "hook", "新的三秒钩子。",
        )
        self.assertFalse(synced)
        self.assertIn("【完整口播文案】用户另写的口播。", unchanged)
        for style in scripts:
            if style == "pain":
                scripts[style] = updated
            else:
                item = scripts[style]
                scripts[style] = (
                    f"【0—3 秒｜开头钩子】{item['hook']}\n"
                    f"【3—12 秒｜核心卖点】{item['selling_points']}\n"
                    f"【12—24 秒｜使用场景】{item['usage_scene']}\n"
                    f"【24—30 秒｜购买引导】{item['call_to_action']}\n"
                    f"【完整口播文案】{item['voiceover']}"
                )
        book = load_workbook(BytesIO(make_excel_bytes(
            "便携咖啡杯", "防漏、轻便、容易清洗", "通勤上班族", 30, scripts,
            date(2026, 10, 19),
        )))
        self.assertEqual(book["痛点营销型"]["B4"].value, "新的三秒钩子。")
        self.assertIn("我手写的卖点", book["痛点营销型"]["B5"].value)
        self.assertIn("新的三秒钩子。", book["痛点营销型"]["B8"].value)

    def test_page_optimization_requires_login_uses_latest_edit_and_counts_request(self):
        with patch("access_control.get_app_password", return_value="测试用密码"), patch(
            "deepseek_service.get_api_key", return_value="测试密钥"
        ), patch(
            "deepseek_service.generate_ai_scripts", return_value=sample_result()
        ), patch(
            "deepseek_service.optimize_script_section", return_value="咖啡放包里，别让它漏。"
        ) as optimize, patch("request_limiter.reserve_ai_request") as reserve:
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
            app.text_input(key="product_name").set_value("便携咖啡杯").run()
            app.text_area(key="selling_points").set_value("防漏、轻便、容易清洗").run()
            app.text_input(key="target_audience").set_value("通勤上班族").run()
            app.radio(key="generation_mode").set_value("AI生成模式").run()
            app.text_input(key="app_password_input").set_value("测试用密码").run()
            app.button(key="unlock_ai").click().run()
            app.button(key="generate_scripts").click().run()
            original = app.text_area(key="script_pain").value
            manual = original.replace("放进通勤包", "我自己改的通勤包画面", 1)
            app.text_area(key="script_pain").set_value(manual).run()
            app.button(key="optimize_pain_hook").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(optimize.call_count, 1)
            self.assertEqual(reserve.call_count, 2)
            self.assertEqual(optimize.call_args.args[6], manual)
            updated = app.text_area(key="script_pain").value
            self.assertEqual(parse_sections(updated)["开头钩子"], "咖啡放包里，别让它漏。")
            self.assertIn("我自己改的通勤包画面", updated)
            self.assertIn("咖啡放包里，别让它漏。", get_voiceover(updated))
            app.button(key="lock_ai").click().run()
            self.assertTrue(app.button(key="optimize_pain_hook").disabled)
            self.assertEqual(optimize.call_count, 1)

    def test_failed_optimization_keeps_manual_text_and_rejects_extra_request(self):
        with patch("access_control.get_app_password", return_value="测试用密码"), patch(
            "deepseek_service.get_api_key", return_value="测试密钥"
        ), patch(
            "deepseek_service.generate_ai_scripts", return_value=sample_result()
        ), patch(
            "deepseek_service.optimize_script_section", side_effect=InvalidAIResponse("局部优化格式错误；已有编辑已保留。")
        ) as optimize, patch("request_limiter.reserve_ai_request") as reserve:
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
            app.text_input(key="product_name").set_value("便携咖啡杯").run()
            app.text_area(key="selling_points").set_value("防漏、轻便、容易清洗").run()
            app.text_input(key="target_audience").set_value("通勤上班族").run()
            app.radio(key="generation_mode").set_value("AI生成模式").run()
            app.text_input(key="app_password_input").set_value("测试用密码").run()
            app.button(key="unlock_ai").click().run()
            app.button(key="generate_scripts").click().run()
            edited = app.text_area(key="script_experience").value.replace("杯子轻便", "用户手动写的杯子轻便")
            app.text_area(key="script_experience").set_value(edited).run()
            app.button(key="optimize_experience_selling_points").click().run()
            self.assertEqual(app.text_area(key="script_experience").value, edited)
            self.assertTrue(any("局部优化格式错误" in item.value for item in app.error))
            self.assertEqual(optimize.call_count, 1)
            self.assertEqual(reserve.call_count, 2)
            app.button(key="optimize_experience_selling_points").click().run()
            self.assertEqual(optimize.call_count, 1)
            self.assertTrue(any("稍等几秒" in item.value for item in app.error))
            self.assertEqual(reserve.call_count, 2)


if __name__ == "__main__":
    unittest.main()
