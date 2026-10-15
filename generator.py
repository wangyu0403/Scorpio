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
        """根据需求、逻辑与表头字段组装 Prompt，强制要求纯 JSON 数组输出。"""
        header_str = "、".join(headers)

        example_obj = {}
        for h in headers:
            example_obj[h] = f"{h}的示例内容"
        example_str = json.dumps([example_obj], ensure_ascii=False, indent=2)

        prompt = f"""你是一位资深测试工程师，请根据下面的需求文档和业务逻辑描述，设计完整、可执行的测试案例。

【需求文档内容开始】
{req_text}
【需求文档内容结束】

【业务逻辑描述内容开始】
{logic_text}
【业务逻辑描述内容结束】

【输出要求】
1. 必须以纯 JSON 数组格式输出，禁止输出 Markdown 代码块标记（禁止出现三反引号 json 之类的标记）。
2. 数组中的每个元素是一个 JSON 对象，代表一条测试案例。
3. 每个对象的 key 必须且只能使用以下字段，顺序保持一致：{header_str}
4. 每个字段的值必须是字符串，不能为空；确实无内容时填写“无”。
5. 测试案例需覆盖正常场景、边界场景、异常场景与权限/兼容性场景，条数不少于 10 条。
6. 除 JSON 数组外，不要输出任何解释性文字、前后缀说明或注释。

【输出格式示例】
{example_str}
"""
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
        llm = LLMFactory.create()
        response = llm.invoke(prompt)

        content = getattr(response, "content", None)
        if content is None:
            content = str(response)
        if isinstance(content, list):
            content = "".join(str(item) for item in content)

        output_path = self.save_output(content, req_name, output_dir)
        return output_path

    # ------------------------------------------------------------------
    # 结果保存
    # ------------------------------------------------------------------
    def save_output(self, content, req_name, output_dir):
        """解析大模型返回的 JSON，转为 DataFrame 并按规范命名保存到 output 目录。"""
        records = self._parse_json_array(content)

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

    @staticmethod
    def _parse_json_array(content):
        """容错解析大模型输出：自动去除 Markdown 代码块标记，截取 JSON 数组。"""
        if content is None:
            raise ValueError("大模型返回内容为空。")

        if isinstance(content, (list, dict)):
            data = content
        else:
            text = str(content).strip()

            # 去掉 ```json / ``` 标记
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text).strip()
            text = re.sub(r"```\s*$", "", text).strip()

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # 容错：截取第一个 [ 到最后一个 ] 之间的内容
                start = text.find("[")
                end = text.rfind("]")
                if start == -1 or end == -1 or end <= start:
                    raise ValueError(
                        f"无法从大模型返回内容中解析出 JSON 数组，原始内容前 500 字符：\n{text[:500]}"
                    )
                try:
                    data = json.loads(text[start:end + 1])
                except json.JSONDecodeError as e:
                    raise ValueError(f"JSON 解析失败：{e}，原始内容前 500 字符：\n{text[:500]}")

        # 兼容模型把数组包在对象里的情况
        if isinstance(data, dict):
            for key in ("testcases", "test_cases", "data", "cases", "result", "list", "测试案例"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
            else:
                data = [data]

        if not isinstance(data, list) or not data:
            raise ValueError("大模型返回内容不是有效的 JSON 数组，或数组为空。")

        # 过滤掉非字典元素
        data = [item for item in data if isinstance(item, dict)]
        if not data:
            raise ValueError("JSON 数组中没有有效的测试案例对象。")

        return data