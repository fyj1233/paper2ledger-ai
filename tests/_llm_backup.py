"""备份/恢复 LLM 配置（settings 表 llm_* 键）。用法：python _llm_backup.py [backup|restore]"""
import glob
import json
import os
import sys
from pathlib import Path

# 默认取本仓库的 backend/data/app.db；测沙箱库时用 SMOKE_DB 覆盖
DB = os.getenv("SMOKE_DB") or str(Path(__file__).resolve().parent.parent / "backend" / "data" / "app.db")
BACKUP = Path(__file__).parent / "_llm_backup.json"

import sqlite3

if sys.argv[1:2] == ["backup"]:
    c = sqlite3.connect(DB)
    rows = c.execute("select key,value from settings where key like 'llm%'").fetchall()
    BACKUP.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"backed up {len(rows)} keys:", [k for k, _ in rows])
elif sys.argv[1:2] == ["restore"]:
    rows = json.loads(BACKUP.read_text(encoding="utf-8"))
    c = sqlite3.connect(DB)
    for k, v in rows:
        c.execute("insert or replace into settings(key,value) values(?,?)", (k, v))
    c.commit()
    cur = c.execute("select key,value from settings where key like 'llm%'").fetchall()
    print(f"restored, now {len(cur)} keys:", [(k, v[:16]) for k, v in cur])
else:
    print("usage: _llm_backup.py backup|restore")
