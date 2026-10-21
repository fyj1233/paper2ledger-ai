# 一纸成账 Paper2Ledger · AI 单据识别与台账智能体

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-智能体-6b3fa0)
![LLM](https://img.shields.io/badge/LLM-OpenAI兼容·主备自动降级-FF6F00)
![OCR](https://img.shields.io/badge/OCR-RapidOCR本地离线-2EA043)

> **继续开发请先读 [`项目手册.md`](项目手册.md)**（完整架构、数据模型、接口清单、已知的坑），
> 任务清单见 [`docs/roadmap.md`](docs/roadmap.md)，开发日志见 [`docs/development-log.md`](docs/development-log.md)，架构设计依据见 [`docs/对标分析.md`](docs/对标分析.md)。

把中小型工厂（螺母等轻工业品）手写的**生产日报、出货单、退货记录、盘点表、收银小票照片**，自动变成能查能算的台账。核心是一条 **AI 提取流水线**：本地 OCR 转文字 → 模板正则 / 规则映射 / 大模型三级级联提取规格条目（品名 / 规格 / 类型 / 数量 / 单价 / 客户）→ 自动匹配产品档案入库；再叠加一个**基于 LangGraph 的台账问答智能体**，用自然语言查产量、出货、库存与异常。未配置大模型时全程降级为规则模式，流程照常可用。

## 界面速览

| AI 助手·台账问答（智能体自主调用 8 个查询工具，流式输出） | AI 周报（图表数字全部后端 SQL 算，LLM 只写文字） |
|:--:|:--:|
| ![AI 助手](docs/images/05-assistant.png) | ![AI 周报](docs/images/14-ai-report.png) |
| **生产看板**（趋势 + 规格占比下钻） | **工厂台账**（明细流水 + 库存结存） |
| ![生产看板](docs/images/02-dashboard.png) | ![工厂台账](docs/images/03-ledger.png) |

<details>
<summary>展开查看其余页面（上传 / 单据详情 / 登录 / 产品档案 / 台账报表 / 模板与字典 / 用户管理 / 系统设置 / 修改密码）</summary>

| 上传单据（多格式拖拽） | 单据详情（提取条目与原文对照） |
|:--:|:--:|
| ![上传单据](docs/images/07-upload.png) | ![单据详情](docs/images/09-document-detail.png) |
| 登录 | 产品档案 |
| ![登录](docs/images/01-login.png) | ![产品档案](docs/images/04-products.png) |
| 台账报表（期间结存流转 + 导出 Excel） | 单据管理 |
| ![台账报表](docs/images/06-reports.png) | ![单据管理](docs/images/08-documents.png) |
| 模板与字典（提取规则可视化） | 系统设置（主备双模型 + 密钥只回尾 4 位） |
| ![模板与字典](docs/images/10-templates.png) | ![系统设置](docs/images/12-settings.png) |
| 用户管理 | 修改密码 |
| ![用户管理](docs/images/11-users.png) | ![修改密码](docs/images/13-change-password.png) |

</details>

## 技术栈

| 层 | 选型 |
|----|------|
| 后端 | Python 3.11+ · FastAPI · SQLAlchemy 2 · SQLite（连接串配置化，可切 PostgreSQL） · APScheduler 式 lifespan 定时任务 |
| 文档解析 | python-docx · openpyxl · pdfplumber · **RapidOCR（onnxruntime 本地离线，无需联网）** |
| AI 层 | LangGraph 多步工具智能体 · AsyncSqliteSaver 会话记忆 · langchain-openai（OpenAI 兼容协议，主备双服务商） |
| 安全 | PyJWT · bcrypt · 三级 RBAC · 操作审计日志 |
| 前端 | Vue 3 · Vite · Element Plus · ECharts · Pinia · Vue Router |
| 部署 | 单进程托管（后端 serve `frontend/dist`）· Docker Compose · Windows/Linux 一键脚本 |

## 技术亮点

1. **三级提取流水线，不依赖外网也能跑**：模板正则 → 规则/表格列映射 → 大模型兜底。未配置 API 时自动降级为规则模式，流程完整可用；每条提取结果带 `source`（template/rule/llm）与 `confidence` 来源标记，可回溯到原文证据。见 `app/services/extractors/`。
2. **主备双大模型自动降级**：主服务商超时 / 5xx / 欠费时自动切换备用接口重试一次，AI 提取、问答、报告三条链路共用同一降级入口（`llm.smart_chat` / `with_fallbacks`），无需人工干预。
3. **AI 不编数字**：周报月报的卡片与图表数据由后端 `report_builder` 按台账口径算好落库，大模型只负责写文字分析——从架构上杜绝 LLM 幻觉造数。
4. **智能体问答带会话记忆**：LangGraph 8 个台账查询工具 + 独立 SQLite checkpointer（`thread_id = chat-{会话id}`），切页不丢上下文；历史回放走只读图，不重新发起模型调用。
5. **库存结存是算出来的，不是存出来的**：期初 / 生产 / 出货 / 报废 / 退货五类型流水单向累加，结存由 SQL 聚合实时得出，改单据即改结存，不存在双写不一致。
6. **可验证的工程习惯**：98 项冒烟回归（配 `mock_llm.py` 离线跑，不依赖外网与真实 Key；报告用例锚定库里最新有数据的日期，换天跑也不会假失败）、SQLite 旧表加列统一走 `migrations.py`、每日定时全量备份 + 跨机还原脚本、接口层与前端路由双重权限校验。

## 功能

| 功能 | 说明 |
|------|------|
| 文档上传解析 | 支持 TXT / CSV / Word(.docx) / Excel(.xlsx) / PDF（文字版）/ 图片小票拍照（OCR 离线识别） |
| AI 智能提取 | 大模型提取规格条目（品名/规格/类型/数量/单价/金额/客户），带来源标记和置信度 |
| 规则兜底模式 | 未配置大模型 API 时，自动使用内置规则提取（关键词 + 表格列映射），保证流程可用 |
| 产品档案 | 多规格产品管理（品名+规格唯一），同名同规格自动匹配，库存预警线 |
| 待确认队列 | 文档里出现新规格时自动进待确认列表，人工一键「新建产品入库 / 认领已有产品 / 忽略」 |
| 工厂台账 | 明细流水（期初/生产/出货/报废/退货五类型）+ 每规格库存结存（自动核算），SQL 分页 |
| 生产看板 | 今日产量/出货卡片、产量出货双线趋势、规格出货占比饼图（点击下钻）、月度对比、库存告急提醒 |
| AI 问答 / 周报月报 | 像聊天一样提问，AI 基于台账数据流式回答（产量/出货/库存/异常预警）；多轮会话记忆（左侧会话栏，切页不丢）；一键生成图表化报告（指标卡片 + 趋势/排行图 + 库存表 + AI 分析，可打印存 PDF） |
| 备用大模型兜底 | 系统设置可配第二家服务商（OpenAI 兼容），主 API 超时/报错/欠费时 AI 提取/问答/报告自动切备用，无需人工干预 |
| 定时自动备份 | 每日到点自动打包数据库 + AI 会话记忆 + 上传文件（默认 23:30，可设置页开关/改时间）；错过时间点服务启动后补跑，自动清理 30 天前旧备份 |
| 多账户权限 | 管理员 / 经理 / 员工三级角色，接口层 + 前端路由双重控制 |
| 用户管理 | 管理员可创建账号、分配角色、重置密码、停用启用 |
| 安全审计 | JWT 登录认证、bcrypt 密码哈希、登录 / 上传 / 删除 / 配置变更等操作审计日志 |

## 权限矩阵

| 功能 | 管理员 | 经理 | 员工 |
|------|:----:|:----:|:----:|
| 上传文档 | ✅ | ✅ | ✅ |
| 查看 / 管理自己的单据 | ✅ | ✅ | ✅ |
| 查看所有人的单据 | ✅ | ✅ | ❌ |
| 生产看板 / 工厂台账 | ✅ | ✅ | ❌ |
| 查看解析出的原始文本 | ✅ | ✅ | ❌ |
| 重新解析 / 删除单据 | ✅ | ✅ | ❌ |
| 下载原始文档 | ✅ | ❌ | ❌ |
| 产品管理 / 用户管理 / 系统设置 / 审计日志 | ✅ | ❌ | ❌ |

## 快速开始（Windows 本地）

```bash
# 1. 安装后端依赖（Python 3.11+）
cd backend
pip install -r requirements.txt

# 2. 安装前端依赖（Node 18+）
cd ../frontend
npm install

# 3. 构建前端（后端会托管 frontend/dist）
node node_modules/vite/bin/vite.js build

# 4. 启动后端
cd ../backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问 http://127.0.0.1:8000 ，默认管理员 `admin / admin123`。首次登录带强制改密标志：**没改密码前，除「读自己 / 改密码」两个接口外全部返回 403**（服务端拦，不是只弹个前端框）。

想直接看提取效果：仓库里带了 10 个模拟单据（`模拟项目/模拟数据/`，TXT×5 / CSV×2 / DOCX / XLSX / 小票照片 JPG，覆盖生产、出货、退货、盘点五类业务），拖到「上传单据」页就能看到规格条目自动入账；产品档案里没有的规格会进「待确认」队列，正好走一遍人工确认那条分支。

开发模式（前端热更新）：双击 `start.bat`，或手动另开终端在 `frontend/` 执行 `node node_modules/vite/bin/vite.js`，访问 http://localhost:5173 。

## 配置大模型 API（留空占位，自己填）

两种方式任选：

**方式一：登录系统 → 系统设置 → 大模型 API 配置**（推荐，填完点"测试连接"验证）

**方式二：编辑 `backend/.env`**

```ini
# 登录令牌签名密钥（必填；不填则每次启动随机生成，重启后需重新登录）
# 生成一个：python -c "import secrets;print(secrets.token_hex(32))"
JWT_SECRET=请换成一串随机字符
# OpenAI 兼容接口地址（会拼接 /chat/completions 调用）
LLM_API_BASE=https://api.deepseek.com/v1
# API Key
LLM_API_KEY=sk-xxxxxxxx
# 模型名称
LLM_MODEL=deepseek-chat
```

> 数据库中配置的值优先于 .env。两者都为空时系统使用内置规则提取模式，流程照常可用。

## 部署到云服务器

### 方式一：一键脚本（无 Docker，推荐）

```bash
# 1. 安装基础环境：Python 3.11+ 与 Node.js 18+（系统级安装）
# 2. 一键安装（自动装依赖 + 构建前端 + 创建 .env）
chmod +x install.sh start.sh && ./install.sh
# 3. 启动（后台常驻）
./start.sh
```

Windows 机器：双击 `install.bat` 安装 → 双击 `start.bat` 启动。

### 方式二：Docker

```bash
git clone https://github.com/fyj1233/paper2ledger-ai.git && cd paper2ledger-ai
# JWT_SECRET 是必填项，缺失时 compose 会直接报错退出
JWT_SECRET=$(python -c "import secrets;print(secrets.token_hex(32))") docker compose up -d --build
```

访问 `http://服务器IP:8000`。数据（SQLite 数据库 + 上传的文件）持久化在 `backend/data/` 目录。建议加一层 Nginx 反代 + HTTPS 后再对公网开放（AI 问答为流式接口，Nginx 需对该路径关闭 `proxy_buffering`）。

**历史数据迁移**：旧机器在「系统设置 → 数据备份」生成 zip 并下载 → 新机器执行：

```bash
cd backend && python restore_backup.py /path/to/backup_xxx.zip   # 有确认提示，自动快照现有数据
```

## 安全与部署边界

公开仓库里的东西会被拿去扫，所以这条线我按"能不能被陌生人利用"来划。

**已经做硬的**

- **令牌**：算法固定 HS256、必须带 `exp`；仓库里不留任何可用的默认密钥——`JWT_SECRET` 缺失时进程内随机生成并打印警告（代价是重启后重新登录），`docker compose` 缺该变量直接拒绝启动。回归用例里有一条专门断言"用公开的旧默认密钥签的 admin 令牌被拒"。
- **首次登录强制改密在服务端拦**：带 `must_change_password` 的账号只能访问 `/api/auth/me` 与 `/api/auth/change-password`，其余接口一律 403（不是只弹前端框）。
- **上传**：文件名 `Path(...).name` 去目录 + 后缀白名单 + 服务端改名 `doc_{id}.{ext}`；请求体只读 `20MB+1` 字节即判限，超大文件不会整份进内存。
- **备份/还原**：还原全程走 `ZipFile.extract()`，含 `../` 的条目被规范掉（防 zip slip）；打包改用 SQLite 备份 API 取一致性快照，正在写入的 `-wal` 不会漏。
- **导出**：Excel 单元格强制文本，单据里以 `=` 开头的品名/客户/依据不会变成公式（CWE-1236）。
- **权限与密钥**：三级 RBAC 在依赖层校验，员工只看得见自己上传的单据；API Key 接口只回 `****后4位`，审计日志不落密钥；口令限 6–72 字节（bcrypt 硬上限，超长在校验层 422 而不是崩成 500）。

**明确没做（内网/单机场景的取舍，别拿去裸奔公网）**

- 没有 TLS 与反向代理层；公网部署请自加 Nginx + HTTPS。
- 登录锁定是单进程内存态，重启清零，无 IP 维度限流；密码策略只校验长度。
- CORS 为 `*`：令牌走 `Authorization` 头而非 Cookie，跨站脚本读不到，但仍应按实际来源收紧。
- LLM API Key 明文存于 SQLite `settings` 表，会随备份 zip 一起流转——**轮换密钥时记得一并清理旧备份包**。
- xlsx/docx 是 zip 容器，尚未加解压膨胀上限；PDF 解析 CPU 密集，单进程部署时并发上传会排队。
- `llm_api_base` 由管理员填写、服务端向该地址发请求，内网部署时这是一条 SSRF 面，信任边界就是管理员账号本身。

## 目录结构

完整清单见 `项目手册.md` §3，核心结构：

```
paper2ledger-ai/
├── 项目手册.md / AGENTS.md / CHANGELOG.md  # 架构手册、开发指南、版本变化
├── docs/roadmap.md / docs/development-log.md   # 任务清单、开发日志
├── install.bat / install.sh / start.bat / start.sh   # 一键安装与启动
├── requirements-frozen.txt（backend/）
├── backend/   # FastAPI 后端（app/ 源码、.env 配置、data/ 生产数据、restore_backup.py）
├── frontend/  # Vue3 前端（src/ 源码、dist/ 构建产物由后端托管）
├── docs/      # 对标分析、调研笔记、界面截图
├── 模拟项目/模拟数据/   # 10 个模拟单据（5 格式 × 5 类业务），可直接上传体验
└── tests/     # smoke_test.py 回归测试、mock_llm.py、测试素材
```

## 常见问题

- **上传 PDF 提示"未提取到文字"**：扫描件 / 图片型 PDF 暂不支持 OCR，请上传文字版 PDF 或改用 Word / Excel。
- **大模型提取失败**：在"系统设置"点"测试连接"排查 API 地址 / Key / 模型名；失败的单据可在列表里"重新解析"。若服务商不稳定，可在"系统设置"配置**备用大模型**（另一家 OpenAI 兼容接口），主 API 报错时自动切换，AI 功能不再中断。
- **忘记管理员密码**：在 backend 目录执行 `python reset_admin.py` 重置为 admin/admin123（不影响其他数据）。
- **切换 PostgreSQL**：在 `.env` 中设置 `DATABASE_URL=postgresql+psycopg://user:pass@host/db` 并安装 `psycopg2-binary` 即可，代码无需改动。
