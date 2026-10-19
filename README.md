# AI短视频营销脚本生成器

这是一个中文 Streamlit 网页。填写产品名称、核心卖点、目标用户和视频时长后，可生成三种风格的营销脚本，直接修改内容，并下载包含四个工作表的 Excel 文件。

## 两种生成模式

- **示例模式**：使用本地固定模板，不调用 AI，也不需要 API Key。
- **AI生成模式**：先用访问密码解锁当前页面会话，再调用 DeepSeek API；需要有效的 DeepSeek API Key 和可用的账户余额。调用可能产生费用。

没有配置密钥或访问密码时，网页仍可使用示例模式、编辑脚本和导出 Excel；AI 模式会拒绝调用。AI 请求失败时会显示原因，不会用示例脚本冒充 AI 结果，也不会清空已编辑内容。

## V1.2 脚本与局部优化

AI 生成会按痛点、实战体验、促销转化三条不同的创作路径写文案。前三秒是短钩子，四个分段时间相加等于所选视频时长；口播过长时会按每段时间预算自动精简，发布前仍建议自己试读。程序会拦截明显缺乏依据的价格、优惠、数字参数和认证，其他产品事实也请人工核对。

每条 AI 脚本下方有“优化前三秒”“强化核心卖点”“优化购买引导”三个按钮。它们每次调用一次 DeepSeek，只替换所选段落；如果完整口播里能准确找到该段原句，会同步替换那一句。如果您单独改写过完整口播，程序会保留您的文字并提示核对。局部优化同样需要先输入访问密码，也计入每日 AI 调用次数；连续优化需间隔 8 秒。示例模式无需密码和 API，不显示优化按钮。Excel 始终读取页面上最新的编辑内容。

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

默认只提供示例模式的完整体验。要开放 AI 生成功能，先在 [DeepSeek 开放平台](https://platform.deepseek.com/)创建可用 API Key，并确认账户余额。在 Streamlit Cloud 中打开此应用的 **Settings → Secrets**，保留已有的 `DEEPSEEK_API_KEY`，另加 `APP_PASSWORD` 一行（把引号中的占位文字换成自己设置的独立、难猜的密码），保存后在网页选择“AI生成模式”测试。不要把真实密钥或密码提交到 GitHub、写进代码或发给访问者。API Key 也可从本机环境变量读取；访问密码仅从 Streamlit Secrets 读取，本机可使用不提交的 `.streamlit/secrets.toml`。

```toml
DEEPSEEK_API_KEY = "在这里填入真实密钥"
APP_PASSWORD = "在这里填入独立且不易猜的访问密码"
```

模型名称在 `settings.toml` 的 `deepseek_model` 中配置，也可用环境变量 `DEEPSEEK_MODEL` 覆盖。当前默认是 DeepSeek 官方文档中的 `deepseek-flash`，通过其兼容 OpenAI 的 Chat Completions HTTPS 接口请求 JSON 结果。

公开网站的 AI 请求上限为全站每天 30 次、每个页面会话每天 5 次；生成和局部优化都计数，请求失败也计数。相同输入重新生成或连续局部优化还要间隔至少 8 秒。输入密码连续错误 5 次会在当前页面会话中暂停登录 15 分钟；打开新会话可绕过这一登录尝试限制，因此应使用不易猜的密码，不要把密码公开分享。AI 请求计数保存在当前服务器的临时文件中，服务重启或更换服务器会重置，因此这些限制只提供基本的用量保护。DeepSeek 平台上的余额和用量管理仍需自行查看。

发布视频前，请人工核对文案中的产品事实、实际价格和活动信息。
