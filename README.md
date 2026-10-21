# Scorpio (Test Case Generator & Requirement Reviewer)

> 基于可切换的大模型接口（LLM），结合需求文档、业务规则和模板，自动生成高质量的测试案例，并支持对需求文档进行多维度智能评审。

## 📖 项目简介
`Scorpio` 是一个用 Python 开发的 AI 测试效能工具。它能读取本地的 Word 需求文档（`.docx`），结合提示词模板，通过大模型 API（默认支持 DeepSeek、OpenAI 等），完成两大核心任务：
1. **生成测试案例**：按照固定的 Excel 模板表头，批量生成结构化、高质量的测试用例。
2. **需求文档评审**：从完整性、清晰度、可测试性三个维度，自动审查需求文档的缺陷。

## ✨ 核心特性
- **双核驱动**：支持“生成测试案例”与“评审需求文档”自由切换。
- **Prompt 模板化**：提示词与代码彻底分离（存放于 `prompts/`），随时调整规则无需改代码。
- **工业级 JSON 容错**：引入 `json-repair` 与防御性 Schema 校验，彻底告别大模型返回脏 JSON 导致的程序崩溃。
- **多环境与安全隔离**：支持 `.env` 管理密钥，内置日志脱敏，防止 API Key 泄露。
- **模型无缝切换**：基于 OpenAI 兼容接口，可轻松切换 `deepseek-flash`、`deepseek-v4-pro` 等模型。

## 📁 项目目录结构
```text
Scorpio/
├── config/                  # 配置模块（多环境加载与安全校验）
├── input/                   # 【输入】放入你的需求文档（.docx）
├── knowledge/               # 【输入】案例生成逻辑描述（.md / .txt，仅生成用例时需要）
├── templates/               # 【输入】测试案例模板（仅表头的 .xlsx，仅生成用例时需要）
├── prompts/                 # 核心提示词模板库
│   ├── test_case_prompt.md  # 生成用例的指令
│   ├── review_completeness.md # 完整性评审指令
│   ├── review_clarity.md      # 清晰度评审指令
│   └── review_testability.md  # 可测试性评审指令
├── output/                  # 【输出】生成的用例/评审报告存放处
├── .env.example             # 环境变量模板
├── .gitignore               # Git 忽略配置
├── requirements.txt         # 依赖清单
├── llm_factory.py           # 大模型工厂类
├── generator.py             # 测试案例生成引擎
├── reviewer.py              # 需求文档评审引擎
└── main.py                  # 程序入口（带终端交互菜单）


🚀 快速开始
1. 安装依赖
建议使用虚拟环境：

bash
python -m venv .venv
# Windows 激活: .\.venv\Scripts\activate
# Mac/Linux 激活: source .venv/bin/activate

pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
2. 配置环境变量
复制 .env.example 为 .env.dev，并填入你的真实 API Key：

text
DEEPSEEK_API_KEY=sk-你的真实APIKey
3. 准备输入文件
在 input/ 放入你的需求文档（注意：必须是 .docx 格式）。

在 knowledge/ 放入规则说明 .md 文件（仅生成用例时需要）。

在 templates/ 放入模板 .xlsx 文件（仅生成用例时需要，第一行必须有表头）。

4. 启动程序
bash
python main.py
程序会自动扫描文件并提示你：

text
请选择要执行的操作：
  [1] 生成测试案例
  [2] 评审需求文档
输入对应数字并回车，生成的文件将自动保存在 output/ 目录下。

体验 V2 平台：在终端运行 uvicorn api:app --reload，然后在浏览器打开 http://127.0.0.1:8000/docs 体验可视化 API 接口。

⚠️ 注意事项 (Important Notes)
文档格式限制：本项目目前仅支持 .docx 格式的 Word 文档。如果手头是老版的 .doc 文件，请先用 Word/WPS 另存为 .docx 后再使用。

输入目录需纯净：input、knowledge、templates 文件夹下每次只能存在一个有效文件。如果放了多个，代码会自动使用找到的第一个并打印警告。

密钥安全：请绝对不要将包含真实 API Key 的 .env.dev 文件推送到 GitHub 等公开仓库。代码中已配置 .gitignore 进行拦截。

大模型幻觉：AI 生成的测试用例或评审意见仅供参考，请测试人员务必进行人工 Review 确认无误后，再录入公司的测试管理系统。

网络环境：调用 DeepSeek 接口时，请确保处于国内直连网络（建议关闭 VPN/代理），否则可能会报连接超时错误。

控制台交互：程序依赖控制台输入进行模式选择，请勿在后台静默运行（如使用 Jenkins/Crontab 定时跑，请在代码中将 choice 变量写死）。

📝 开发计划 (Todo)
☑ 搭建基础架构与多环境配置
☑ 实现测试案例生成功能（支持动态扫描与 JSON 强容错）
☑ 实现需求文档三维度智能评审功能
☑ 重构 Prompt，实现模板化分离
□ V2 架构升级：接入 FastAPI，打造前后端分离的 Web 测试平台