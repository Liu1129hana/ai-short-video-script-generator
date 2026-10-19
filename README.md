# AI短视频营销脚本生成器

这是一个中文 Streamlit 网页。填写产品名称、核心卖点、目标用户和视频时长后，可生成三种风格的营销脚本，直接修改内容，并下载包含四个工作表的 Excel 文件。

## 两种生成模式

- **示例模式**：使用本地固定模板，不调用 AI，也不需要 API Key。
- **AI生成模式**：调用 Google Gemini API，需要有效的 API Key 和该密钥所属项目的 API 访问权限。调用可能产生用量或费用。

没有配置密钥时，网页仍可使用示例模式、编辑脚本和导出 Excel。当前 Gemini 项目若返回 403，说明项目没有 API 访问权限；配置同一项目的密钥到云端也不会解决这一问题。

## 在 Mac 上运行

在项目目录执行：

```bash
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

然后打开 `http://127.0.0.1:8501/`。使用期间保持终端窗口打开；按 `Control + C` 停止。没有虚拟环境时，先用 Python 3.13 创建 `.venv`，再运行 `.venv/bin/python -m pip install -r requirements.txt`。

## 部署到 Streamlit Community Cloud

1. 将本项目的程序文件、`requirements.txt`、`settings.toml` 和本说明提交到 GitHub 仓库。`.gitignore` 已排除本机密钥、虚拟环境、Excel 成品及临时文件。
2. 在 [Streamlit Community Cloud](https://share.streamlit.io/) 选择 **Create app** → **Deploy a public app from GitHub**，选择仓库、分支和入口文件 `app.py`。选择 Python 3.13，然后部署。
3. 云端网址可分享给知道链接的人。每位访问者的页面会话各自独立；要保留脚本，请及时下载 Excel。

默认只提供示例模式的完整体验。若将来要开放 AI 生成功能，请先确认 Gemini 项目有访问权限，并考虑公开网页的访问者会共用云端 API 配额。确认后，在 Streamlit Cloud 的应用设置中通过 **Secrets** 添加 `GEMINI_API_KEY`；绝不要把真实密钥提交到 GitHub、写进代码或发给访问者。模型名称在 `settings.toml` 的 `gemini_model` 中配置，也可用环境变量 `GEMINI_MODEL` 覆盖。

发布视频前，请人工核对文案中的产品事实、实际价格和活动信息。
