import os
import shutil
import tempfile
import traceback

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse

from config.settings import api_key
from generator import TestCaseGenerator
from reviewer import RequirementReviewer

app = FastAPI(title="Test Case & Requirement Review API")

# 生成结果的输出目录（与临时上传目录分离，避免清理时误删返回值）
OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "api_outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _safe_rmtree(path: str) -> None:
    """安全删除目录，忽略清理阶段的异常。"""
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def _safe_remove(path: str) -> None:
    """安全删除单个文件，忽略清理阶段的异常。"""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


async def _save_upload(upload: UploadFile, target_path: str) -> None:
    """将上传文件流写入目标路径。"""
    try:
        with open(target_path, "wb") as f:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    finally:
        await upload.close()


@app.post("/api/generate")
async def generate(
        docx_file: UploadFile = File(...),
        md_file: UploadFile = File(...),
        xlsx_file: UploadFile = File(...),
):
    """接收 docx / md / xlsx 三个文件，生成测试用例 Excel 并返回。"""
    tmp_dir = tempfile.mkdtemp(prefix="gen_upload_")
    try:
        docx_path = os.path.join(tmp_dir, docx_file.filename or "input.docx")
        md_path = os.path.join(tmp_dir, md_file.filename or "input.md")
        xlsx_path = os.path.join(tmp_dir, xlsx_file.filename or "input.xlsx")

        await _save_upload(docx_file, docx_path)
        await _save_upload(md_file, md_path)
        await _save_upload(xlsx_file, xlsx_path)

        try:
            # 1. 传入 api_key
            generator = TestCaseGenerator(api_key=api_key)

            # 2. 提取需求文件名
            req_name = os.path.splitext(docx_file.filename or "input")[0]

            # 3. 严格按照 generate 的签名传参，并输出到 OUTPUT_DIR
            output_path = generator.generate(
                req_path=docx_path,
                logic_path=md_path,
                template_path=xlsx_path,
                output_dir=OUTPUT_DIR,
                req_name=req_name
            )
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"生成测试用例失败: {e}")

        if not output_path or not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="生成结果文件不存在")

        return FileResponse(
            path=output_path,
            filename=os.path.basename(output_path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    finally:
        _safe_rmtree(tmp_dir)


@app.post("/api/review")
async def review(docx_file: UploadFile = File(...)):
    """接收 docx 文件，生成需求评审 Excel 报告并返回。"""
    tmp_dir = tempfile.mkdtemp(prefix="review_upload_")
    try:
        docx_path = os.path.join(tmp_dir, docx_file.filename or "input.docx")
        await _save_upload(docx_file, docx_path)

        try:
            # 1. 传入 api_key
            reviewer = RequirementReviewer(api_key=api_key)

            # 2. 提取需求文件名
            req_name = os.path.splitext(docx_file.filename or "input")[0]

            # 3. 严格按照 review 的签名传参，并输出到 OUTPUT_DIR
            output_path = reviewer.review(
                req_path=docx_path,
                output_dir=OUTPUT_DIR,
                req_name=req_name
            )
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"需求评审失败: {e}")

        if not output_path or not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="评审报告文件不存在")

        return FileResponse(
            path=output_path,
            filename=os.path.basename(output_path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    finally:
        _safe_rmtree(tmp_dir)


if __name__ == "__main__":
    import uvicorn

    # 在 Mac 上通常可以直接跑 0.0.0.0:8000
    uvicorn.run(app, host="0.0.0.0", port=8000)