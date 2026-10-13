"""多环境配置加载模块（开发 / 测试 / 预发布 / 生产）。

安全说明：
    系统环境变量优先级高于本地 .env 文件。生产环境推荐通过 K8s / 配置中心
    注入环境变量，不依赖本地 .env 文件，以避免密钥随代码仓库泄露。
    ``load_dotenv()`` 默认不会覆盖已存在的系统环境变量（override=False），
    因此当 APP_ENV、DEEPSEEK_API_KEY 等已由运行环境注入时，本地文件会被忽略。
"""

import os

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1. 解析当前运行环境
# ---------------------------------------------------------------------------
# 读取系统环境变量 APP_ENV；未设置时默认使用 'dev'。
APP_ENV = os.getenv("APP_ENV", "dev")

# ---------------------------------------------------------------------------
# 2. 根据 APP_ENV 动态拼接并加载对应的环境文件
# ---------------------------------------------------------------------------
# 例如：dev -> .env.dev，test -> .env.test，staging -> .env.staging
# 说明：这里的路径以项目根目录为基准。为了兼容从任意工作目录启动，
#       我们基于当前文件位置（config/ 的上一级）计算根目录。
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(BASE_DIR, f".env.{APP_ENV}")

# load_dotenv 默认 override=False：系统环境变量优先级高于本地文件。
load_dotenv(dotenv_path=ENV_FILE, override=False)

# ---------------------------------------------------------------------------
# 3. 读取并校验 API Key（防御性编程）
# ---------------------------------------------------------------------------
api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise ValueError("未检测到 DEEPSEEK_API_KEY，请检查当前环境配置！")


def mask_key(key: str) -> str:
    """对 API Key 做脱敏处理，仅保留前 4 位，其余用 * 代替。

    例如：``sk-4abcdefg`` -> ``sk-4***``。绝不要打印完整密钥。
    """
    if not key:
        return "***"
    return f"{key[:4]}***"
