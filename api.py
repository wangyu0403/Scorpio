# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
import traceback
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    File,
    UploadFile,
    HTTPException,
    Header,
    Query,
    Depends,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from config.settings import api_key
from generator import TestCaseGenerator
from reviewer import RequirementReviewer
from database import TaskRecord, DeleteAuditLog, get_db


app = FastAPI(title="Test Case & Requirement Review API")

# ================= 基础配置 =================

load_dotenv()
HISTORY_DIR = os.getenv(
    "HISTORY_DIR", os.path.join(tempfile.gettempdir(), "scorpio_history")
)

if not os.path.isabs(HISTORY_DIR):
    HISTORY_DIR = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), HISTORY_DIR
    )
os.makedirs(HISTORY_DIR, exist_ok=True)

# 文件保留天数：生成/评审完成后 purge_due_at = 当前时间 + 7 天
RETENTION_DAYS = 7

# 任务状态常量（与数据库中的 status 字段保持一致）
STATUS_ACTIVE = "ACTIVE"
STATUS_PENDING_PURGE = "PENDING_PURGE"


# ================= 通用工具 =================

def _utcnow() -> datetime:
    """统一使用 naive UTC 时间，避免 SQLite DateTime 时区比较报错。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _purge_due_at() -> datetime:
    """文件过期清理时间：当前时间 + 7 天。"""
    return _utcnow() + timedelta(days=RETENTION_DAYS)


def _not_found() -> HTTPException:
    """统一 404：文件不存在 / 无权访问 / 状态不可下载，一律同一响应，避免信息泄露。"""
    return HTTPException(status_code=404, detail="文件不存在或无权访问")


def _safe_rmtree(path: str) -> None:
    """安全删除目录，忽略清理阶段的异常。"""
    try:
        shutil.rmtree(path, ignore_errors=True)
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


def _persist_output(temp_output_path: str, task_id: str) -> str:
    """把临时目录里的产物移动到持久化目录，返回最终路径。"""
    file_ext = os.path.splitext(temp_output_path)[1]
    final_path = os.path.join(HISTORY_DIR, f"{task_id}{file_ext}")
    shutil.move(temp_output_path, final_path)
    return final_path


def _create_task_record(
    db: Session,
    task_id: str,
    owner_account_id: str,
    file_path: str,
    original_filename: str,
    task_type: str,
) -> TaskRecord:
    """落库：记录归属账号、文件路径、状态与 7 天清理时间。"""
    record = TaskRecord(
        task_id=task_id,
        owner_account_id=owner_account_id,
        file_path=file_path,
        original_filename=original_filename,
        task_type=task_type,
        status=STATUS_ACTIVE,
        purge_due_at=_purge_due_at(),
        created_at=_utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ================= 生成 / 评审 =================

@app.post("/api/generate")
async def generate(
    docx_file: UploadFile = File(...),
    md_file: UploadFile = File(...),
    xlsx_file: UploadFile = File(...),
    x_account_id: str = Header(..., alias="x_account_id"),
    db: Session = Depends(get_db),
):
    """接收 docx / md / xlsx，生成测试用例并落库（归属 x_account_id）。"""
    tmp_dir = tempfile.mkdtemp(prefix="gen_upload_")
    try:
        docx_path = os.path.join(tmp_dir, docx_file.filename or "input.docx")
        md_path = os.path.join(tmp_dir, md_file.filename or "input.md")
        xlsx_path = os.path.join(tmp_dir, xlsx_file.filename or "input.xlsx")

        await _save_upload(docx_file, docx_path)
        await _save_upload(md_file, md_path)
        await _save_upload(xlsx_file, xlsx_path)

        try:
            generator = TestCaseGenerator(api_key=api_key)
            req_name = os.path.splitext(docx_file.filename or "input")[0]
            temp_output_path = generator.generate(
                req_path=docx_path,
                logic_path=md_path,
                template_path=xlsx_path,
                output_dir=tmp_dir,
                req_name=req_name,
            )
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"生成测试用例失败: {e}")

        if not temp_output_path or not os.path.exists(temp_output_path):
            raise HTTPException(status_code=500, detail="生成结果文件不存在")

        original_filename = os.path.basename(temp_output_path)
        task_id = str(uuid.uuid4())
        final_path = _persist_output(temp_output_path, task_id)
        _create_task_record(
            db=db,
            task_id=task_id,
            owner_account_id=x_account_id,
            file_path=final_path,
            original_filename=original_filename,
            task_type="GENERATE",
        )

        return {
            "code": 200,
            "message": "生成成功",
            "data": {
                "task_id": task_id,
                "filename": original_filename,
                "download_url": f"/api/files/{task_id}",
                "purge_due_at": _purge_due_at().isoformat(),
            },
        }
    finally:
        _safe_rmtree(tmp_dir)


@app.post("/api/review")
async def review(
    docx_file: UploadFile = File(...),
    x_account_id: str = Header(..., alias="x_account_id"),
    db: Session = Depends(get_db),
):
    """接收 docx，生成需求评审报告并落库（归属 x_account_id）。"""
    tmp_dir = tempfile.mkdtemp(prefix="review_upload_")
    try:
        docx_path = os.path.join(tmp_dir, docx_file.filename or "input.docx")
        await _save_upload(docx_file, docx_path)

        try:
            reviewer = RequirementReviewer(api_key=api_key)
            req_name = os.path.splitext(docx_file.filename or "input")[0]
            temp_output_path = reviewer.review(
                req_path=docx_path,
                output_dir=tmp_dir,
                req_name=req_name,
            )
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"需求评审失败: {e}")

        if not temp_output_path or not os.path.exists(temp_output_path):
            raise HTTPException(status_code=500, detail="评审报告文件不存在")

        original_filename = os.path.basename(temp_output_path)
        task_id = str(uuid.uuid4())
        final_path = _persist_output(temp_output_path, task_id)
        _create_task_record(
            db=db,
            task_id=task_id,
            owner_account_id=x_account_id,
            file_path=final_path,
            original_filename=original_filename,
            task_type="REVIEW",
        )

        return {
            "code": 200,
            "message": "评审成功",
            "data": {
                "task_id": task_id,
                "filename": original_filename,
                "download_url": f"/api/files/{task_id}",
                "purge_due_at": _purge_due_at().isoformat(),
            },
        }
    finally:
        _safe_rmtree(tmp_dir)


# ================= 历史记录 =================

@app.get("/api/history")
async def get_history(
    x_account_id: str = Header(..., alias="x_account_id"),
    db: Session = Depends(get_db),
):
    """仅返回当前账号名下、状态为 ACTIVE 的记录。"""
    records = (
        db.query(TaskRecord)
        .filter(
            TaskRecord.owner_account_id == x_account_id,
            TaskRecord.status == STATUS_ACTIVE,
        )
        .order_by(TaskRecord.created_at.desc())
        .all()
    )

    items = [
        {
            "task_id": r.task_id,
            "filename": r.original_filename or os.path.basename(r.file_path or ""),
            "task_type": r.task_type,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "purge_due_at": r.purge_due_at.isoformat() if r.purge_due_at else None,
            "download_url": f"/api/files/{r.task_id}",
        }
        for r in records
    ]

    return {
        "code": 200,
        "message": "ok",
        "data": {"total": len(items), "items": items},
    }


# ================= 下载 =================

@app.get("/api/files/{task_id}")
async def download_file(
    task_id: str,
    x_account_id: str = Header(..., alias="x_account_id"),
    db: Session = Depends(get_db),
):
    """安全下载：记录不存在 / 归属不符 / 状态非 ACTIVE / 文件缺失 一律 404。"""
    record = db.query(TaskRecord).filter(TaskRecord.task_id == task_id).first()
    if record is None:
        raise _not_found()

    if record.owner_account_id != x_account_id:
        raise _not_found()

    if record.status != STATUS_ACTIVE:
        raise _not_found()

    if record.purge_due_at and record.purge_due_at < _utcnow():
        raise _not_found()

    if not record.file_path or not os.path.exists(record.file_path):
        raise _not_found()

    return FileResponse(
        path=record.file_path,
        filename=record.original_filename or os.path.basename(record.file_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ================= 管理端：申请删除 =================

@app.post("/api/admin/files/{task_id}/request-delete")
async def request_delete_file(
    task_id: str,
    reason: str = Query(..., description="删除原因"),
    x_admin_id: str = Header(..., alias="x_admin_id"),
    db: Session = Depends(get_db),
):
    """不物理删除文件：写入审计日志，并把状态置为 PENDING_PURGE 等待定时清理。"""
    record = db.query(TaskRecord).filter(TaskRecord.task_id == task_id).first()
    if record is None:
        raise _not_found()

    if record.status == STATUS_PENDING_PURGE:
        return {
            "code": 200,
            "message": "该文件已处于待清理状态，无需重复申请",
            "data": {"task_id": task_id, "status": record.status},
        }

    try:
        db.add(
            DeleteAuditLog(
                task_id=task_id,
                admin_id=x_admin_id,
                reason=reason,
                created_at=_utcnow(),
            )
        )
        record.status = STATUS_PENDING_PURGE
        db.commit()
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"写入删除审计日志失败: {e}")

    return {
        "code": 200,
        "message": "已提交删除申请，等待定时任务清理",
        "data": {"task_id": task_id, "status": STATUS_PENDING_PURGE},
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)