# -*- coding: utf-8 -*-
"""数据库连接、会话管理与 ORM 模型定义。"""

import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    text
)
from sqlalchemy.orm import declarative_base, sessionmaker

# 加载 .env 环境变量
load_dotenv(".env.dev")

# 数据库连接字符串
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./scorpio.db")

# ================= 自动建库逻辑（MySQL 专属） =================
if DATABASE_URL.startswith("mysql"):
    try:
        # 1. 提取出数据库名称（例如 scorpio_db）
        db_name = DATABASE_URL.split("/")[-1].split("?")[0]

        # 2. 拼凑一个不带数据库名的根连接（连接到 MySQL 服务器本身）
        base_url = DATABASE_URL.rsplit("/", 1)[0] + "/"

        # 3. 连上服务器，执行建库 SQL
        temp_engine = create_engine(base_url)
        with temp_engine.connect() as conn:
            # 注意：这里的字符集设置必须带上，否则中文会乱码
            conn.execute(
                text(f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
            conn.commit()
        temp_engine.dispose()
        print(f"✅ 成功确保数据库 {db_name} 存在！")
    except Exception as e:
        print(f"⚠️ 自动建库失败，请检查 MySQL 权限或连接: {e}")
# =============================================================

# 根据数据库类型，生成正式的业务 engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True
    )

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

Base = declarative_base()


class TaskRecord(Base):
    """任务记录表：保存每一次生成/评审任务的文件与归属信息。"""
    __tablename__ = "scorpio_tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, index=True, nullable=False)
    owner_account_id = Column(String(128), index=True, nullable=False)
    file_path = Column(String(1024), nullable=True)
    original_filename = Column(String(255), nullable=True)
    task_type = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="ACTIVE")
    purge_due_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class DeleteAuditLog(Base):
    """删除审计日志：记录任务文件被删除的请求与原因。"""
    __tablename__ = "scorpio_delete_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), index=True, nullable=True)
    admin_id = Column(String(128), nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


def init_db() -> None:
    """初始化数据库，创建所有已定义的表。"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI 依赖注入使用：提供 Session 并在请求结束后自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()