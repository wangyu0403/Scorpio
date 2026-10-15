# -*- coding: utf-8 -*-
"""
main.py
程序入口：
    1. 动态获取项目根目录
    2. 自动扫描 input / knowledge / templates 文件夹（文件名不写死）
    3. 调用 TestCaseGenerator 生成测试案例并保存到 output/
"""

import os
import sys

from config.settings import APP_ENV, api_key, mask_key
from generator import TestCaseGenerator, find_single_file


def get_project_root():
    """获取项目根目录（main.py 所在目录）"""
    return os.path.dirname(os.path.abspath(__file__))


def main():
    root_dir = get_project_root()

    input_dir = os.path.join(root_dir, "input")
    knowledge_dir = os.path.join(root_dir, "knowledge")
    templates_dir = os.path.join(root_dir, "templates")
    output_dir = os.path.join(root_dir, "output")

    try:
        print("=" * 60)
        print("测试案例自动生成工具")
        print("=" * 60)
        
        # 打印环境信息（安全脱敏，不泄露完整 Key）
        print(f"当前运行环境: {APP_ENV}")
        print(f"当前 API Key: {mask_key(api_key)}")
        print(f"项目根目录：{root_dir}")
        print("-" * 60)

        # 动态扫描三个输入文件夹，文件名不写死
        req_path = find_single_file(input_dir, [".docx", ".doc"])
        logic_path = find_single_file(knowledge_dir, [".md", ".txt"])
        template_path = find_single_file(templates_dir, [".xlsx"])

        # 用需求文档名（不含后缀）作为输出文件前缀
        req_name = os.path.splitext(os.path.basename(req_path))[0]

        print(f"需求文档：{os.path.basename(req_path)}")
        print(f"逻辑描述：{os.path.basename(logic_path)}")
        print(f"模板文件：{os.path.basename(template_path)}")
        print(f"输出目录：{output_dir}")
        print("-" * 60)

        generator = TestCaseGenerator(api_key=api_key)
        output_path = generator.generate(
            req_path=req_path,
            logic_path=logic_path,
            template_path=template_path,
            output_dir=output_dir,
            req_name=req_name,
        )

        print("-" * 60)
        print(f"保存成功：{output_path}")
        print("=" * 60)

    except FileNotFoundError as e:
        print("-" * 60)
        print(f"[错误] 文件未找到：{e}")
        print("请检查 input / knowledge / templates 文件夹内是否有对应格式的文件。")
        print("=" * 60)
        sys.exit(1)

    except ValueError as e:
        print("-" * 60)
        print(f"[错误] 数据校验失败：{e}")
        print("=" * 60)
        sys.exit(1)

    except Exception as e:
        print("-" * 60)
        print(f"[错误] 生成失败：{type(e).__name__} - {e}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()