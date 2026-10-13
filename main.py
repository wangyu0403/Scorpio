"""Scorpio 入口：加载多环境配置并测试大模型连通性。"""

from config.settings import APP_ENV, api_key, mask_key

# 打印当前运行环境（绝不打印完整 API Key）。
print(f"当前运行环境: {APP_ENV}")
# 如需日志，仅打印脱敏后的 Key（前 4 位 + 星号）。
print(f"当前 API Key: {mask_key(api_key)}")

from llm_factory import LLMFactory


def main() -> None:
    """实例化 LLMFactory 并调用大模型进行测试。"""
    llm = LLMFactory(api_key=api_key)

    messages = [
        {"role": "user", "content": "当前使用的是什么模型？"},
    ]

    print("正在调用大模型...")
    reply = llm.chat(messages)
    print("模型回复:", reply)


if __name__ == "__main__":
    main()
