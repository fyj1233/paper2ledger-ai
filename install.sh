#!/usr/bin/env bash
# 一纸成账 Paper2Ledger - Linux/macOS 一键安装（云端手动部署用）
set -e
cd "$(dirname "$0")"
echo "============================================"
echo "  一纸成账 Paper2Ledger - 一键安装"
echo "============================================"

echo "[1/5] 检查 Python..."
command -v python3 >/dev/null || { echo "[错误] 未安装 Python 3.11+"; exit 1; }
python3 --version

echo "[2/5] 检查 Node.js..."
command -v node >/dev/null || { echo "[错误] 未安装 Node.js 18+"; exit 1; }
node --version

echo "[3/5] 安装后端依赖..."
cd backend
pip3 install -r requirements.txt

echo "[4/5] 安装前端依赖..."
cd ../frontend
[ -d node_modules ] || npm install

echo "[5/5] 构建前端..."
node node_modules/vite/bin/vite.js build

if [ ! -f ../backend/.env ]; then
    cp ../.env.example ../backend/.env
    echo "已从模板创建 backend/.env"
fi
python3 ../backend/setup_env.py

echo
echo "============================================"
echo "  安装完成！运行 ./start.sh 启动系统"
echo "============================================"
