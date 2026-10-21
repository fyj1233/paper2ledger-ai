"""从备份 zip 还原数据（跨机器迁移的标准做法）。

流程：旧机器在「系统设置 → 数据备份」生成 zip 并下载
      → 新机器把 zip 放到任意位置 → 运行本脚本还原 → 重启服务

用法：
    cd backend
    python restore_backup.py backups/backup_20260902_031352.zip
    python restore_backup.py C:\\Downloads\\backup_20260902_031352.zip

脚本会：解压 app.db 和 uploads/ 覆盖到 backend/data/ 下，并把现有数据先行备份为
data_before_restore/ 目录（不会直接丢弃）。
"""

import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
UPLOAD_DIR = DATA_DIR / "uploads"


def main() -> None:
    if len(sys.argv) != 2:
        print("用法：python restore_backup.py <备份zip路径>")
        sys.exit(1)

    zip_path = Path(sys.argv[1])
    if not zip_path.exists():
        print(f"[错误] 备份文件不存在：{zip_path}")
        sys.exit(1)

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if "app.db" not in names:
            print("[错误] 这不是一个有效的系统备份（缺少 app.db）")
            sys.exit(1)
        upload_count = sum(1 for n in names if n.startswith("uploads/"))
        memory = "含" if "agent_memory.db" in names else "不含"
        print(f"备份内容：数据库 1 个文件（{memory} AI 会话记忆），上传文件 {upload_count} 个")

    answer = input(
        "警告：还原将覆盖当前所有经营数据！现有数据会先备份到 data_before_restore/。\n"
        "确认还原请输入 yes："
    ).strip().lower()
    if answer != "yes":
        print("已取消")
        sys.exit(0)

    # 现有数据快照
    keep_dir = DATA_DIR / f"data_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    keep_dir.mkdir(parents=True, exist_ok=True)
    current_db = DATA_DIR / "app.db"
    if current_db.exists():
        shutil.copy2(current_db, keep_dir / "app.db")
    if UPLOAD_DIR.exists():
        shutil.copytree(UPLOAD_DIR, keep_dir / "uploads", dirs_exist_ok=True)
    print(f"现有数据已快照到：{keep_dir.name}")

    with zipfile.ZipFile(zip_path) as zf:
        zf.extract("app.db", DATA_DIR)
        if "agent_memory.db" in zf.namelist():
            zf.extract("agent_memory.db", DATA_DIR)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        for name in zf.namelist():
            if name.startswith("uploads/") and not name.endswith("/"):
                # 用 extract() 而非手工拼路径：它会把 ../ 等穿越成分规范掉，防 zip slip
                zf.extract(name, DATA_DIR)

    print("还原完成！请重启后端服务使数据生效。")


if __name__ == "__main__":
    main()
