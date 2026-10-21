# ---- 前端构建 ----
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN node node_modules/vite/bin/vite.js build

# ---- 后端运行 ----
FROM python:3.12-slim
# OpenCV 在 Linux 上需要的系统库（OCR 图片识别用）
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend
COPY --from=frontend /build/dist ./frontend/dist

EXPOSE 8000
WORKDIR /app/backend
VOLUME ["/app/backend/data"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
