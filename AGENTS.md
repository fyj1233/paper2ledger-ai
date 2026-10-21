# AGENTS.md — 智能体接手须知

你正在接手「一纸成账 Paper2Ledger」（螺母等轻工业品的每日台账——文档上传 → LLM/模板提取规格条目 → 产品匹配 → 台账/看板；2026-09-02 定名，前身「经营分析系统」→「财账分析系统」）。

## 必读（按顺序）
1. **`项目手册.md`** — 完整架构、数据模型、API 清单、23 条已知坑
2. **`PROGRESS.md`** — 任务清单（从这里领任务）+ 更新日志
3. `docs/对标分析.md` — 架构设计依据

## 铁律（违反会破坏生产数据或约定）
1. 禁止删除 `backend/data/`（生产数据库与上传文件）
2. 禁止修改 `backend/.env` 中 LLM 配置的值
3. 禁止把项目数据发送到外部地址；禁止 git push
4. 只做 PROGRESS.md 第一个未勾选任务，完成即写日志停止
5. SQLite 给旧表加列必须走 `app/migrations.py`（create_all 不改旧表）
6. 跑 smoke_test 前备份 LLM 配置（settings 表 llm* 键，含主 llm_* 三键与备用 llm_backup_* 三键），跑完恢复——测试开头会主动清空 LLM 配置（保证文档走模板/规则提取不依赖外网）。备份/恢复用 `tests/_llm_backup.py backup|restore`
7. 安全红线（本仓库是公开的，别把这些改回去）：`JWT_SECRET` 不许留可用的默认值或占位符（缺失即随机生成，见 config.py）；账号口令不许写进 README/手册/PROGRESS/测试代码，测试脚本一律读环境变量；Excel 导出新增列必须走 `services/xlsx_out.append_row`（防公式注入）；解压备份包只能用 `ZipFile.extract`，不许手工拼路径写文件

## 验证（每次改动后）
```bash
cd tests && python smoke_test.py                          # 98 项回归，需后端在运行（地址用 SMOKE_BASE 覆盖），可重复跑
cd frontend && node node_modules/vite/bin/vite.js build   # ★ 前端必须 rebuild，勿用 npm run build
```

## 常见坑速记
- 本机 `npm run dev/build` 不可用（cmd 找不到 node），一律直调 vite.js
- Git Bash curl 发中文 JSON 要写成 UTF-8 文件 `--data-binary @file`
- AI 问答是 LangGraph 智能体（`app/services/agent.py`），流式协议 `{"delta"}` / `{"tool"}`；mock 测试用 `tests/mock_llm.py`，测完清空 LLM 配置
- 台账五类型：initial/production/return 加库存，shipment/scrap 减库存；数量恒正
- AI 助手已切台账口径（8 工具查 ledger_entries），insights/report_builder 是它的数据层；模型无 relationship，取品名要查 products 表拼映射
- AI 问答有会话记忆：LangGraph checkpointer 存 `backend/data/agent_memory.db`（`services/agent_memory.py`，thread_id=`chat-{session_id}`）——勿用 glob 在 data 目录找 app.db（会命中它），工具一律硬编码路径
- AI 报告的图表数字由后端 report_builder 算好存 reports.charts（cards/trend/spec_rank/inventory 四块），LLM 只写文字分析——改口径别让 LLM 编数
- LLM 有主备双配置：settings 表 llm_*（主）+ llm_backup_*（备用兜底）；提取/报告走 `llm.smart_chat`、智能体走 `with_fallbacks`，主挂自动切备用——升级 langchain 后必须重跑冒烟"主挂切备用"用例
- 定时备份在 lifespan 的 asyncio 循环（`services/auto_backup.py`），核心打包逻辑在 `services/backup_service.py`（手动/定时共用，勿在路由里重复实现）；备份包含 app.db + agent_memory.db + uploads，当日已有备份则跳过

---

## 附录：给新智能体/新会话的开场提示词模板（用户复制用）

**① 继续开发（标准开场）**
```
你接手一个已完成大半的项目「一纸成账 Paper2Ledger」（FastAPI + Vue3，螺母等轻工业品的每日台账管理系统，运行端口 8000）。
请按顺序快速熟悉，不要跳过：
1. 读 AGENTS.md（接手须知、铁律、验证命令）
2. 读 项目手册.md（完整架构、数据模型、API 清单、23 条已知坑）
3. 读 PROGRESS.md（任务清单与更新日志，从第一个未勾选任务继续）
读完先向我简报三件事：项目现状、你理解的下一步任务、你的实施计划。经我确认后再动手写代码。
开发约定：所有文案用中文；改动后必须跑 tests/smoke_test.py 回归 + 在 frontend 执行 node node_modules/vite/bin/vite.js build；
禁止删除 backend/data、禁止修改 backend/.env 的 LLM 配置、禁止把数据发到外部。
```

**② 只修 Bug**
```
项目出现此问题：<描述现象/贴报错>
请先读 AGENTS.md 和 项目手册.md 第 9 节（已知坑）定位原因，告诉我根因和修复方案，经我确认后修复，
并用 tests/smoke_test.py 回归验证。
```

**③ 只做问答/使用咨询**
```
请读 项目手册.md 和 README.md，回答我的问题：<问题>
```

**④ 从备份迁移到新机器**
```
请读 README.md 的部署章节和 项目手册.md 第 11 节，帮我在本机完成安装启动，
并用 backend/restore_backup.py 还原我提供的备份 zip。
```
