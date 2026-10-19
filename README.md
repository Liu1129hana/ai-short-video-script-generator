# AI短视频营销脚本生成器

这是一个中文 Streamlit 网页。填写产品名称、核心卖点、目标用户和视频时长后，可生成三种风格的营销脚本，直接修改内容，并下载包含四个工作表的 Excel 文件。

## 两种生成模式

- **示例模式**：使用本地固定模板，不调用 AI，也不需要 API Key。
- **AI生成模式**：调用 DeepSeek API，需要有效的 DeepSeek API Key 和可用的账户余额。调用可能产生费用。

没有配置密钥时，网页仍可使用示例模式、编辑脚本和导出 Excel。AI 请求失败时会显示原因，不会用示例脚本冒充 AI 结果，也不会清空已编辑内容。

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

默认只提供示例模式的完整体验。要开放 AI 生成功能，先在 [DeepSeek 开放平台](https://platform.deepseek.com/)创建可用 API Key，并确认账户余额。在 Streamlit Cloud 中打开此应用的 **Settings → Secrets**，添加下面一行（把引号中的占位文字换成真实密钥），保存后在网页选择“AI生成模式”测试。不要把真实密钥提交到 GitHub、写进代码或发给访问者。本机也可以使用同名环境变量或不提交的 `.streamlit/secrets.toml`。

```toml
DEEPSEEK_API_KEY = "在这里填入真实密钥"
```

模型名称在 `settings.toml` 的 `deepseek_model` 中配置，也可用环境变量 `DEEPSEEK_MODEL` 覆盖。当前默认是 DeepSeek 官方文档中的 `deepseek-flash`，通过其兼容 OpenAI 的 Chat Completions HTTPS 接口请求 JSON 结果。

公开网站的 AI 请求上限为全站每天 30 次、每个页面会话每天 5 次；请求失败也计数。此计数保存在当前服务器的临时文件中，服务重启或更换服务器会重置，因此它只提供基本的用量保护。DeepSeek 平台上的余额和用量管理仍需自行查看。

发布视频前，请人工核对文案中的产品事实、实际价格和活动信息。
