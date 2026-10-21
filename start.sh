#!/usr/bin/env bash
# 一纸成账 Paper2Ledger - Linux 启动（后台常驻，日志在 backend/run.log）
set -e
cd "$(dirname "$0")"

if [ ! -f backend/.env ]; then
    cp .env.example backend/.env
    echo "已从模板创建 backend/.env"
fi
python3 backend/setup_env.py
if [ ! -f frontend/dist/index.html ]; then
    echo "[错误] 未检测到前端构建产物，请先运行 ./install.sh"
    exit 1
fi

cd backend
nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > run.log 2>&1 &
echo "系统已启动：http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 127.0.0.1):8000"
echo "停止命令：pkill -f 'uvicorn app.main' ；日志：backend/run.log"
