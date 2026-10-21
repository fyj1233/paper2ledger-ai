# AGENTS.md

面向 AI 编程助手（Codex / Claude Code / Cursor / Aider 等）的仓库说明书，同时也是人类贡献者的开发指南。
README.md 面向使用者，本文面向**要改这个仓库代码的人**。

## 项目概览

一纸成账 Paper2Ledger：面向中小型工厂（螺母等轻工业品）的每日台账系统。上传单据 → 解析转文字 →
模板/规则/大模型三级级联提取规格条目 → 产品匹配自动出入库 → 台账流水、看板与报表；
另有一个 LangGraph 智能体负责台账问答与图表化周报/月报。

后端 FastAPI + SQLAlchemy 2 + SQLite（`backend/`，默认端口 8000）；前端 Vue 3 + Vite + Element Plus + ECharts
（`frontend/`，构建产物由后端托管）。角色三级：admin / manager / employee。

## 文档索引

| 文件 | 内容 |
|---|---|
| `README.md` | 功能与界面截图、安装部署、**安全与部署边界** |
| `项目手册.md` | 完整架构、数据模型、API 清单、已知坑 |
| `CHANGELOG.md` | 按版本的功能变化 |
| `docs/development-log.md` | 开发日志：逐条记录实现方式与验证结果 |
| `docs/roadmap.md` | 任务清单与后续计划 |
| `docs/对标分析.md` | 架构设计依据（为什么长成这样） |

## 环境与构建

```bash
pip install -r backend/requirements.txt          # 后端依赖（Python 3.11+）
cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend && npm install
cd frontend && node node_modules/vite/bin/vite.js build   # 前端构建产物由后端托管
```

改后端代码需要重启进程；改前端代码必须重新 build，否则页面仍是旧产物。
新增 Python 依赖同步写进 `backend/requirements.txt`，前端依赖写进 `frontend/package.json`。

## 测试

```bash
cd tests && SMOKE_ADMIN_PASSWORD=<管理员口令> python smoke_test.py    # 98 项回归，需后端已启动
cd tests && python mock_llm.py                                       # 本地 mock 大模型（8001），离线测 AI 分支
```

- 冒烟覆盖 RBAC、五种格式解析、三条提取路径、产品匹配与待确认、台账、看板、备份与自动备份、
  AI 流式问答、会话记忆、可视化报告、主备兜底切换，以及安全用例（公开默认密钥伪造令牌被拒、
  未改初始密码时接口被拦）。可重复运行，开头会自愈清理上次残留。
- 冒烟会**清空 LLM 配置**（保证文档走模板/规则、不依赖外网）。跑前备份、跑后恢复：
  `python tests/_llm_backup.py backup|restore`。
- 地址与账号一律走环境变量：`SMOKE_BASE` / `SMOKE_ADMIN_PASSWORD` / `SMOKE_ZS_USERNAME` / `SMOKE_ZS_PASSWORD`。
- 完成的判定标准：前端 build 通过；接口改动有 curl 或冒烟验证；涉及页面的改动在浏览器里看过、控制台无报错。

## 代码风格

- 界面文案、注释、提交说明一律中文；风格跟随现有文件，不引入新框架。
- 给 SQLite 旧表加列必须走 `app/migrations.py`（`create_all` 不会改旧表）。
- 手动备份与定时备份共用 `services/backup_service.py`，不要在路由里重复实现打包逻辑。
- 台账是流水账：没有独立的库存表，结存一律由 `ledger_entries` 实时聚合；数量恒正，方向由五类型决定
  （initial/production/return 加，shipment/scrap 减）。
- 报告与看板的数字由后端 SQL 计算，LLM 只写文字分析。改这条链路时不要让模型产出事实性数字。

## 安全注意事项

本仓库是公开的，以下约束被破坏等于直接把漏洞发布出去。

- `JWT_SECRET` 不得留可用的默认值或模板占位符：缺失时进程内随机生成并告警，`docker compose` 缺该变量直接拒绝启动。
- 首次登录强制改密由服务端拦截（`app/deps.py`），不要退回"只弹前端"。
- 账号口令不得写进 README、文档或测试代码，测试脚本一律读环境变量。
- Excel 导出新增列必须走 `services/xlsx_out.append_row`，防止以 `=` 开头的单据文本被写成公式（CWE-1236）。
- 解压备份包只能用 `ZipFile.extract`，不要手工拼路径写文件（zip slip）。
- 上传处理保持"文件名去目录 + 后缀白名单 + 服务端改名 + 只多读 1 字节判限"的写法。
- 新增涉及单据/台账数据的接口要做员工数据隔离：只能看到自己上传的内容，参考 `documents.py` 的 `_can_view`。
- 生产数据红线：不删除 `backend/data/`，不修改 `backend/.env` 里的 LLM 配置值，不把业务数据发往外部地址。

## 提交与 PR

- 一次提交做一件事；改动后跑冒烟与前端 build。
- 每个里程碑在 `docs/development-log.md` 追加一条，写清实现方式与验证结果（含失败过的路径）。
- 版本级变化同步进 `CHANGELOG.md`。
