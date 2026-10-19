# -*- coding: utf-8 -*-
"""
main.py 程序入口：
    1. 动态获取项目根目录
    2. 终端交互选择：生成测试案例 或 评审需求文档
    3. 仅在需要时扫描对应的文件夹（防止空文件夹导致评审闪退）
"""

import os
import sys
import traceback

from config.settings import APP_ENV, api_key, mask_key
from generator import TestCaseGenerator, find_single_file
from reviewer import RequirementReviewer


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
        print(" Scorpio - 测试案例自动生成与需求评审工具")
        print("=" * 60)

        # 打印环境信息（安全脱敏，不泄露完整 Key）
        print(f"当前运行环境: {APP_ENV}")
        print(f"当前 API Key: {mask_key(api_key)}")
        print(f"项目根目录：{root_dir}")
        print("-" * 60)

        # 1. 无论做什么操作，都需要先找到需求文档
        req_path = find_single_file(input_dir, [".docx"])
        req_name = os.path.splitext(os.path.basename(req_path))[0]

        print(f"需求文档：{os.path.basename(req_path)}")
        print("-" * 60)

        # 2. 终端交互：选择要执行的操作
        print("请选择要执行的操作：")
        print("  [1] 生成测试案例")
        print("  [2] 评审需求文档")
        choice = input("请输入数字 (1 或 2，默认 1): ").strip()
        print("-" * 60)

        if choice == "2":
            # ---- 需求文档评审 ----
            print("正在执行：需求文档评审")
            print(f"输出目录：{output_dir}")
            print("-" * 60)

            reviewer = RequirementReviewer(api_key=api_key)

            # 评审不需要模板和逻辑文档
            output_path = reviewer.review(
                req_path=req_path,
                output_dir=output_dir,
                req_name=req_name,
            )
            # review() 总会落盘报告（无问题时为表头空表），output_path 必然有值
            print(f"评审报告保存成功：{output_path}")

        elif choice in ("1", ""):
            # ---- 生成测试案例 ----
            print("正在执行：生成测试案例")

            # 只有在生成测试案例时，才去扫描逻辑描述和模板
            logic_path = find_single_file(knowledge_dir, [".md", ".txt"])
            template_path = find_single_file(templates_dir, [".xlsx"])

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
            print(f"测试案例保存成功：{output_path}")

        else:
            print(f"[错误] 无效的输入 '{choice}'，请重新运行并输入 1 或 2。")
            sys.exit(1)

    except FileNotFoundError as e:
        print("-" * 60)
        print(f"[错误] 文件未找到：{e}")
        print("请检查对应的文件夹内是否有正确的文件。")
        sys.exit(1)

    except ValueError as e:
        print("-" * 60)
        print(f"[错误] 数据校验失败：{e}")
        sys.exit(1)

    except Exception as e:
        print("-" * 60)
        print(f"[错误] 发生未捕获异常：{type(e).__name__} - {e}")
        traceback.print_exc()
        sys.exit(1)

    finally:
        # 无论报错退出还是正常结束，都保证打印最后的分隔线，保持终端整洁
        print("=" * 60)


if __name__ == "__main__":
    main()