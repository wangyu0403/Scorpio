#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2026/11/5 17:24
# @Author  : wangyu
# @Site    : https://github.com/wangyu0403
# @File    : cleaner.py
# @Software: PyCharm

import os
import time
from datetime import datetime
from database import SessionLocal, TaskRecord, DeleteAuditLog

# -*- coding: utf-8 -*-
import os
import time
from datetime import datetime, timezone
from database import SessionLocal, TaskRecord, DeleteAuditLog


def run_cleaner():
    print(f"[{datetime.now()}] 🧹 清理服务已启动，开始轮询...")

    while True:
        db = SessionLocal()
        try:
            # 统一使用 UTC 时间（因为 api.py 里写入的 purge_due_at 是 UTC 时间）
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

            # 核心防并发：使用 with_for_update(skip_locked=True)
            # 这样如果多个实例同时查，只有一个能抢到这批数据，其他实例会直接跳过
            tasks_to_delete = db.query(TaskRecord).filter(
                (TaskRecord.purge_due_at <= now_utc) |
                (TaskRecord.status == "PENDING_PURGE")
            ).with_for_update(skip_locked=True).all()

            if tasks_to_delete:
                print(f"[{datetime.now()}] 发现 {len(tasks_to_delete)} 个待清理文件")

                for task in tasks_to_delete:
                    # 1. 物理删除文件（原则二、三）
                    if task.file_path and os.path.exists(task.file_path):
                        try:
                            os.remove(task.file_path)
                            print(f" -> 物理文件已删除: {task.file_path}")
                        except Exception as e:
                            print(f" -> 物理文件删除失败 {task.file_path}: {e}")

                    # 2. 元数据留痕，只标记状态，不删记录（原则五）
                    task.status = "DELETED"
                    task.file_path = "PURGED"  # 抹除物理路径信息

                    # 3. 补一条审计日志
                    if not db.query(DeleteAuditLog).filter(DeleteAuditLog.task_id == task.task_id).first():
                        sys_log = DeleteAuditLog(
                            task_id=task.task_id,
                            admin_id="SYSTEM_CLEANER",  # ⚠️ 注意：如果你表里叫 requester_id，请改这里
                            reason="定时过期自动清理"
                        )
                        db.add(sys_log)

            db.commit()  # 提交事务，释放锁

        except Exception as e:
            print(f"[{datetime.now()}] 清理异常，但不退出服务: {e}")
            db.rollback()
        finally:
            db.close()

        try:
            time.sleep(3600)  # 睡 1 小时
        except KeyboardInterrupt:
            # 优雅退出
            print("清理服务已手动停止。")
            break


if __name__ == "__main__":
    run_cleaner()