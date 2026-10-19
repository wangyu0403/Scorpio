# -*- coding: utf-8 -*-
"""
generator.py
测试案例生成核心模块：
    1. 动态扫描 input / knowledge / templates 文件夹（文件名不写死）
    2. 读取需求文档（.docx）、逻辑描述（.md / .txt）、模板表头（.xlsx）
    3. 组装 Prompt，调用 LLMFactory 生成测试案例
    4. 解析 JSON 结果并保存为 Excel 到 output/
"""

import os
import re
import json
from datetime import datetime
from wsgiref import headers

import docx
import pandas as pd

from llm_factory import LLMFactory


def find_single_file(folder_path, extensions):
    """
    动态扫描文件夹，返回第一个匹配后缀的文件路径。

    :param folder_path: 待扫描的文件夹路径
    :param extensions: 允许的后缀集合，例如 [".docx", ".doc"]，大小写不敏感
    :return: 匹配到的文件绝对路径
    :raises FileNotFoundError: 文件夹不存在，或文件夹内没有匹配文件
    """
    folder_path = os.path.abspath(folder_path)
    normalized_ext = tuple(
        e.lower() if str(e).startswith(".") else "." + str(e).lower()
        for e in extensions
    )

    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"文件夹不存在：{folder_path}")

    matched_files = []
    for name in sorted(os.listdir(folder_path)):
        # 跳过 Excel / Word 临时文件与隐藏文件
        if name.startswith("~$") or name.startswith("."):
            continue
        full_path = os.path.join(folder_path, name)
        if not os.path.isfile(full_path):
            continue
        if os.path.splitext(name)[1].lower() in normalized_ext:
            matched_files.append(full_path)

    if not matched_files:
        raise FileNotFoundError(
            f"文件夹 {folder_path} 中没有找到后缀为 {list(normalized_ext)} 的文件，"
            f"请确认该文件夹不为空。"
        )

    if len(matched_files) > 1:
        print(f"[警告] 文件夹 {folder_path} 中匹配到 {len(matched_files)} 个文件，"
              f"将使用第一个：{os.path.basename(matched_files[0])}")
        for f in matched_files[1:]:
            print(f"[警告]    已忽略：{os.path.basename(f)}")

    return matched_files[0]


class TestCaseGenerator:
    """测试案例生成器"""

    def __init__(self, api_key=None):
        self.api_key = api_key

    # ------------------------------------------------------------------
    # 文件读取
    # ------------------------------------------------------------------
    def read_word(self, file_path):
        """读取 .docx 需求文档的全部文本（含表格）。老版 .doc 直接报错。"""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"需求文档不存在：{file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".doc":
            raise ValueError(
                f"暂不支持老版 .doc 格式，请另存为 .docx 后重试（文件：{file_path}）"
            )
        if ext != ".docx":
            raise ValueError(f"需求文档必须是 .docx 格式，当前为：{ext}")

        document = docx.Document(file_path)

        paragraphs = []
        for p in document.paragraphs:
            text = p.text.strip()
            if text:
                paragraphs.append(text)

        # 需求文档里经常用表格描述字段，这里一并读取
        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                line = " | ".join([c for c in cells if c])
                if line:
                    paragraphs.append(line)

        if not paragraphs:
            raise ValueError(f"需求文档内容为空：{file_path}")

        return "\n".join(paragraphs)

    def read_text(self, file_path):
        """读取 .md / .txt 逻辑描述文本（自动尝试多种编码）。"""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"逻辑描述文件不存在：{file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in (".md", ".txt"):
            raise ValueError(f"逻辑描述文件必须是 .md 或 .txt，当前为：{ext}")

        content = None
        last_error = None
        for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError as e:
                last_error = e
                continue

        if content is None:
            raise ValueError(f"无法解码文件 {file_path}：{last_error}")

        content = content.strip()
        if not content:
            raise ValueError(f"逻辑描述文件内容为空：{file_path}")

        return content

    def read_template_headers(self, file_path):
        """读取模板 Excel 第一行表头，返回字段列表。"""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"模板文件不存在：{file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext != ".xlsx":
            raise ValueError(f"模板文件必须是 .xlsx 格式，当前为：{ext}")

        # nrows=0 表示只读取表头，不读取数据行
        df = pd.read_excel(file_path, nrows=0, engine="openpyxl")

        headers = []
        for col in df.columns:
            name = str(col).strip()
            if not name or name.lower().startswith("unnamed"):
                continue
            headers.append(name)

        if not headers:
            raise ValueError(f"模板文件第一行表头为空，无法确定字段：{file_path}")

        return headers

    # ------------------------------------------------------------------
    # Prompt 组装
    # ------------------------------------------------------------------
    def build_prompt(self, req_text, logic_text, headers):
        """从独立模板文件中读取 Prompt，并替换变量。"""
        # 1. 获取项目根目录及模板文件路径
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(base_dir, "prompts", "test_case_prompt.md")

        # 2. 读取模板文件内容
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"找不到 Prompt 模板文件：{prompt_path}，请检查 prompts 目录是否存在。")

        # 3. 构造示例 JSON 对象
        header_str = "、".join(headers)
        example_obj = {h: f"{h}的示例内容" for h in headers}
        example_str = json.dumps([example_obj], ensure_ascii=False, indent=2)

        # 4. 替换模板占位符（注意：用 replace 而不是 format，防止 JSON 示例中的大括号引发冲突）
        prompt = template.replace("{req_text}", req_text) \
                         .replace("{logic_text}", logic_text) \
                         .replace("{header_str}", header_str) \
                         .replace("{example_str}", example_str)

        return prompt

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def generate(self, req_path, logic_path, template_path, output_dir, req_name=None):
        """
        串联完整流程：读需求 -> 读逻辑 -> 读模板 -> 调用大模型 -> 保存 Excel。
        返回生成的 Excel 文件绝对路径。
        """
        if not req_name:
            req_name = os.path.splitext(os.path.basename(req_path))[0]

        print(f"[1/4] 正在读取需求文档：{os.path.basename(req_path)}")
        req_text = self.read_word(req_path)

        print(f"[2/4] 正在读取逻辑描述：{os.path.basename(logic_path)}")
        logic_text = self.read_text(logic_path)

        print(f"[3/4] 正在读取模板表头：{os.path.basename(template_path)}")
        headers = self.read_template_headers(template_path)
        print(f"      模板字段：{headers}")

        prompt = self.build_prompt(req_text, logic_text, headers)

        print("[4/4] 正在调用大模型生成测试案例 ...")
        # llm = LLMFactory.create()
        # response = llm.invoke(prompt)
        llm = LLMFactory(api_key=self.api_key)
        response = llm.chat([{"role": "user", "content": prompt}])

        # content = getattr(response, "content", None)
        content = response if isinstance(response, str) else str(response)
        if content is None:
            content = str(response)
        if isinstance(content, list):
            content = "".join(str(item) for item in content)

        output_path = self.save_output(content, req_name, output_dir, headers)
        return output_path

    # ------------------------------------------------------------------
    # 结果保存
    # ------------------------------------------------------------------
    def save_output(self, content, req_name, output_dir, headers):
        """解析大模型返回的 JSON，转为 DataFrame 并按规范命名保存到 output 目录。"""
        records = self._parse_json_array(content, expected_headers=headers)

        df = pd.DataFrame(records)

        # 去掉全空的列，保证表格整洁
        df = df.dropna(axis=1, how="all")

        if df.empty:
            raise ValueError("解析后的测试案例为空，无法保存。")

        os.makedirs(output_dir, exist_ok=True)

        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{req_name}-测试案例-{current_time}.xlsx"
        output_path = os.path.join(output_dir, file_name)

        df.to_excel(output_path, index=False, engine="openpyxl")
        return os.path.abspath(output_path)

    # @staticmethod
    # def _parse_json_array(content):
    #     """容错解析大模型输出：自动去除 Markdown 代码块标记，截取 JSON 数组。"""
    #     if content is None:
    #         raise ValueError("大模型返回内容为空。")
    #
    #     if isinstance(content, (list, dict)):
    #         data = content
    #     else:
    #         text = str(content).strip()
    #
    #         # 去掉 ```json / ``` 标记
    #         text = re.sub(r"^```[a-zA-Z]*\s*", "", text).strip()
    #         text = re.sub(r"```\s*$", "", text).strip()
    #
    #         try:
    #             data = json.loads(text)
    #         except json.JSONDecodeError:
    #             # 容错：截取第一个 [ 到最后一个 ] 之间的内容
    #             start = text.find("[")
    #             end = text.rfind("]")
    #             if start == -1 or end == -1 or end <= start:
    #                 raise ValueError(
    #                     f"无法从大模型返回内容中解析出 JSON 数组，原始内容前 500 字符：\n{text[:500]}"
    #                 )
    #             try:
    #                 data = json.loads(text[start:end + 1])
    #             except json.JSONDecodeError as e:
    #                 raise ValueError(f"JSON 解析失败：{e}，原始内容前 500 字符：\n{text[:500]}")
    #
    #     # 兼容模型把数组包在对象里的情况
    #     if isinstance(data, dict):
    #         for key in ("testcases", "test_cases", "data", "cases", "result", "list", "测试案例"):
    #             if isinstance(data.get(key), list):
    #                 data = data[key]
    #                 break
    #         else:
    #             data = [data]
    #
    #     if not isinstance(data, list) or not data:
    #         raise ValueError("大模型返回内容不是有效的 JSON 数组，或数组为空。")
    #
    #     # 过滤掉非字典元素
    #     data = [item for item in data if isinstance(item, dict)]
    #     if not data:
    #         raise ValueError("JSON 数组中没有有效的测试案例对象。")
    #
    #     return data



    @staticmethod
    def _parse_json_array(content: str, expected_headers: list = None) -> list:
        """从大模型返回的文本中提取并解析 JSON 数组（防御性加强版）。"""
        import json_repair

        if not content or not isinstance(content, str) or not content.strip():
            raise ValueError("模型返回内容为空或非字符串")

        #  坑3防御：拦截截断。括号数量不对大概率是被 max_tokens 截断了
        if content.count("[") != content.count("]"):
            raise ValueError(f"返回的 JSON 括号不匹配（可能因长度限制被截断），原始内容前 200 字符：\n{content[:200]}")

        # 使用 json_repair 解析
        try:
            result = json_repair.loads(content)
        except Exception as e:
            raise ValueError(f"JSON 修复解析彻底失败: {e}，原始内容前 500 字符：\n{content[:500]}")

        #  坑2防御：它不抛异常，而是返回怪东西（空串、None、数字）
        if not isinstance(result, (list, dict)):
            raise ValueError(
                f"解析结果类型异常（{type(result).__name__}），可能是模型返回了错误信息，原始内容：\n{content[:200]}")

        #  坑4防御：说明文字里的方括号被合并成嵌套数组（如 [[1], [{"name": "c1"}]]）
        if isinstance(result, list) and result and isinstance(result[0], list):
            # 提取包含字典最多的那个子列表
            all_lists = [item for item in result if isinstance(item, list)]
            if all_lists:
                best_list = max(all_lists, key=lambda x: sum(1 for i in x if isinstance(i, dict)))
                result = best_list

        #  坑1防御：包装层解包（处理 {"error": ...} 或 {"data": {"list": [...]}}）
        if isinstance(result, dict):
            # 严格限制白名单，且只找第一层或两层嵌套
            for key in ("testcases", "test_cases", "cases", "list"):
                val = result.get(key)
                if isinstance(val, list):
                    result = val
                    break
                # 处理两层嵌套：{"code":0, "data": {"list": [...]}}
                if isinstance(val, dict) and "list" in val and isinstance(val["list"], list):
                    result = val["list"]
                    break
            else:
                # 如果没命中白名单，且包含 "error"，直接拦截
                if "error" in result or "code" in result and result.get("code") != 200:
                    raise ValueError(f"模型返回了异常信封: {result}")
                # 兜底：可能是单个合法案例对象
                result = [result]

        if not isinstance(result, list):
            raise ValueError(f"最终解析结果不是列表，实际类型: {type(result).__name__}")

        #  坑3 & 坑5防御：结构校验（Schema Validation）。单引号 ,} 被切坏或截断的数据，在这里会被拦下。
        valid_cases = []
        for item in result:
            if not isinstance(item, dict):
                print(f"[警告] 丢弃非字典元素: {item}")
                continue

            # 如果传入了期望的表头字段，检查这个案例是否缺失了必填字段
            if expected_headers:
                missing_keys = [h for h in expected_headers if h not in item]
                # 如果是空字典，或者缺失了超过一半的字段，判定为废数据
                if not item or len(missing_keys) > len(expected_headers) / 2:
                    print(f"[警告] 丢弃残缺案例（缺失字段 {missing_keys}）: {item}")
                    continue

            valid_cases.append(item)

        if not valid_cases:
            raise ValueError(f"解析后没有合法的测试案例，原始结果: {result}")

        return valid_cases