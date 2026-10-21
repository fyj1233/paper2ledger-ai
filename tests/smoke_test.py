"""全功能冒烟测试：覆盖所有接口、全部上传格式、提取流水线、RBAC、备份。

用法：cd tests && python smoke_test.py
（会临时使用 mock LLM 测 AI 功能，结束后自动清理配置与测试数据）
"""

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx
import jwt

# 账号口令一律来自环境变量，不写死在代码里（本文件会随仓库公开）
BASE = os.getenv("SMOKE_BASE", "http://127.0.0.1:8000")
ADMIN_PASSWORD = os.getenv("SMOKE_ADMIN_PASSWORD", "admin123")
ZS_USERNAME = os.getenv("SMOKE_ZS_USERNAME", "zhangsan")
ZS_PASSWORD = os.getenv("SMOKE_ZS_PASSWORD", "")
FIXTURES = Path(__file__).parent / "fixtures"
results: list[tuple[str, bool, str]] = []
created_docs: list[int] = []
cleanup_record_ids: list[int] = []


def check(name: str, cond, extra: str = ""):
    results.append((name, bool(cond), extra))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  ({extra})" if extra and not cond else ""))


def wait_doc(client: httpx.Client, headers, doc_id: int, timeout=40):
    for _ in range(timeout // 2):
        time.sleep(2)
        r = client.get(f"{BASE}/api/documents/{doc_id}", headers=headers)
        status = r.json().get("status")
        if status in ("parsed", "failed"):
            return r.json()
    return {"status": "timeout"}


def data_anchor(client: httpx.Client, headers) -> str | None:
    """取库里最新一条流水的日期作为报告锚点。

    报告按"今天所在周/月"取数，演示数据停在历史月份时直接算当前周会得到空区间，
    断言就会假失败——锚到真实有数据的那天，用例才与运行日期无关。
    """
    r = client.get(f"{BASE}/api/ledger", headers=headers, params={"page": 1, "page_size": 1})
    items = (r.json() or {}).get("items") or []
    return items[0]["entry_date"] if items else None


def main():
    client = httpx.Client(timeout=90)

    # ── 基础与认证 ──
    r = client.get(f"{BASE}/api/health")
    check("健康检查", r.status_code == 200)

    r = client.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    check("管理员登录", r.status_code == 200, r.text[:100])
    if r.status_code != 200:
        print(f"[中止] 管理员登录失败：请用 SMOKE_ADMIN_PASSWORD 指定密码（当前用的是 {ADMIN_PASSWORD!r}）")
        sys.exit(1)
    admin = {"Authorization": f"Bearer {r.json()['access_token']}"}
    check("管理员已改初始密码", not r.json()["user"]["must_change_password"],
          "初始密码下除改密外的接口都会被 403 拦截")

    # 员工账号：优先用环境变量里提供的；没有就临时建一个 smoke_emp，收尾时删掉
    emp_password = ZS_PASSWORD or secrets.token_hex(8)
    emp_username = ZS_USERNAME if ZS_PASSWORD else "smoke_emp"
    created_emp_id = None
    r = client.post(f"{BASE}/api/auth/login", json={"username": emp_username, "password": emp_password})
    if r.status_code != 200:
        for u in client.get(f"{BASE}/api/users", headers=admin).json():
            if u["username"] == emp_username:
                client.delete(f"{BASE}/api/users/{u['id']}", headers=admin)
        rr = client.post(f"{BASE}/api/users", headers=admin, json={
            "username": emp_username, "password": emp_password, "role": "employee"})
        check("临时创建员工账号", rr.status_code == 201, rr.text[:100])
        created_emp_id = rr.json().get("id")
        r = client.post(f"{BASE}/api/auth/login", json={"username": emp_username, "password": emp_password})
    check("员工登录", r.status_code == 200, r.text[:100])
    emp = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "wrong"})
    check("错误密码返回401", r.status_code == 401)

    # ── RBAC ──
    forged = jwt.encode({"sub": "admin"}, "dev-secret-change-me", algorithm="HS256")
    check("旧公开默认密钥签的令牌被拒",
          client.get(f"{BASE}/api/users", headers={"Authorization": f"Bearer {forged}"}).status_code == 401)
    check("员工访问看板被拒", client.get(f"{BASE}/api/dashboard/overview", headers=emp).status_code == 403)
    check("员工访问用户列表被拒", client.get(f"{BASE}/api/users", headers=emp).status_code == 403)
    check("员工访问备份被拒", client.get(f"{BASE}/api/backup", headers=emp).status_code == 403)
    check("员工访问模板被拒", client.get(f"{BASE}/api/templates", headers=emp).status_code == 403)
    check("员工访问台账被拒", client.get(f"{BASE}/api/ledger", headers=emp).status_code == 403)
    check("员工访问待确认被拒", client.get(f"{BASE}/api/ledger/pending", headers=emp).status_code == 403)
    check("无token访问单据被拒", client.get(f"{BASE}/api/documents").status_code == 401)

    # ── 字典 ──
    r = client.get(f"{BASE}/api/dicts", headers=admin)
    check("字典接口", r.status_code == 200 and "category" in r.json() and "payment" in r.json())
    r = client.post(f"{BASE}/api/dicts", headers=admin, json={"dict_type": "category", "name": "测试分类XYZ"})
    check("新增字典项", r.status_code == 201, r.text[:100])
    test_dict_id = r.json().get("id")
    r = client.delete(f"{BASE}/api/dicts/{test_dict_id}", headers=admin)
    check("删除字典项", r.status_code == 200)

    # ── 清理上次运行残留（幂等：上次中途崩溃也能自愈重跑）──
    smoke_files = {"smoke_生产日报.txt", "smoke_新规格.txt", "smoke_忽略.txt", "smoke_llm.txt",
                   "factory_flow.csv", "factory_report.docx", "factory_ledger.xlsx", "factory_receipt.png"}
    for d in client.get(f"{BASE}/api/documents", headers=admin).json():
        if (d.get("filename") or "") in smoke_files:
            client.delete(f"{BASE}/api/documents/{d['id']}", headers=admin)
    for t in client.get(f"{BASE}/api/templates", headers=admin).json():
        if t["name"] == "冒烟测试生产模板":
            client.delete(f"{BASE}/api/templates/{t['id']}", headers=admin)
    # 单据删除会级联删除其台账/待确认条目，之后残留产品才可删除
    for p in client.get(f"{BASE}/api/products", headers=admin).json():
        if p["name"] in ("冒烟螺母", "新规格螺母"):
            client.delete(f"{BASE}/api/products/{p['id']}", headers=admin)

    # ── 清空 LLM 配置：前面文档走模板/规则提取（确定性），不依赖外网；AI 段再配 mock ──
    # 注意：真实 LLM 配置需提前备份（tests/_llm_backup.py backup），跑完 restore 恢复
    client.put(f"{BASE}/api/settings", headers=admin, json={
        "llm_api_base": "", "llm_api_key": "", "llm_model": ""})

    # ── 产品 + 模板：创建 → 试提取 → 上传命中 ──
    r = client.post(f"{BASE}/api/products", headers=admin, json={
        "name": "冒烟螺母", "spec": "M11×1.1", "unit": "千件", "category": "螺母"})
    check("创建测试产品", r.status_code == 201, r.text[:100])
    smoke_product_id = r.json().get("id")

    tpl = {
        "name": "冒烟测试生产模板",
        "keywords": ["生产日报"],
        "fields": {
            "date": [r"(\d{1,2}\s*月\s*\d{1,2}\s*日)"],
            "product_name": [r"^([\u4e00-\u9fa5]{1,12}?)\s+M\d"],
            "spec": [r"(M\d+(?:[×x]\d+(?:\.\d+)?)?)"],
            "entry_type": [r"(生产|出货|报废|退货|期初)"],
            "quantity": [r"生产\s*([\d.]+)\s*千件"],
            "unit": [r"[\d.]+\s*(千件)"],
        },
        "is_active": True,
    }
    r = client.post(f"{BASE}/api/templates", headers=admin, json=tpl)
    check("创建提取模板", r.status_code == 201, r.text[:100])
    tpl_id = r.json().get("id")

    tpl_text = (
        "2026年9月3日 生产日报\n"
        "冒烟螺母 M11×1.1 测试级：生产 52 千件，报废 0.5 千件\n"
        "冒烟螺母 M11×1.1 测试级：生产 38 千件\n"
    )
    r = client.post(f"{BASE}/api/templates/test", headers=admin, json={"text": tpl_text, "template_id": tpl_id})
    body = r.json()
    check("模板试提取", r.status_code == 200 and body.get("matched") and len(body.get("items") or []) == 2, r.text[:150])
    check("模板试提取类型正确", body.get("items") and all(i["entry_type"] == "production" for i in body["items"]))

    files = {"file": ("smoke_生产日报.txt", tpl_text.encode("utf-8"), "text/plain")}
    r = client.post(f"{BASE}/api/documents/upload", headers=emp, files=files)
    doc_id = r.json().get("id")
    created_docs.append(doc_id)
    doc = wait_doc(client, emp, doc_id)
    check("TXT 走模板提取", doc["status"] == "parsed" and doc["item_count"] == 2 and doc["pending_count"] == 0,
          json.dumps(doc, ensure_ascii=False)[:200])
    check("模板条目来源标记", doc["items"] and all(i["source"] == "template" for i in doc["items"]))
    check("模板条目匹配到产品", doc["items"] and all(i["product_name"] == "冒烟螺母" for i in doc["items"]))

    # ── 其余格式（LLM 未配置 → 规则提取）──
    for fname in ("factory_flow.csv", "factory_report.docx", "factory_ledger.xlsx", "factory_receipt.png"):
        path = FIXTURES / fname
        files = {"file": (fname, path.read_bytes(), "application/octet-stream")}
        r = client.post(f"{BASE}/api/documents/upload", headers=emp, files=files)
        did = r.json().get("id")
        created_docs.append(did)
        doc = wait_doc(client, emp, did, timeout=60 if fname.endswith("png") else 30)
        total = (doc.get("item_count") or 0) + (doc.get("pending_count") or 0)
        check(f"{fname.split('.')[-1].upper()} 解析+条目提取", doc["status"] == "parsed" and total >= 1,
              json.dumps(doc, ensure_ascii=False)[:200])

    # ── 待确认条目：生成 → 列表 → 新建产品入库 → 忽略 ──
    text = "2026年9月4日 生产日报\n新规格螺母 M99×9.9 特殊：生产 25 千件\n"
    files = {"file": ("smoke_新规格.txt", text.encode("utf-8"), "text/plain")}
    r = client.post(f"{BASE}/api/documents/upload", headers=emp, files=files)
    did = r.json().get("id")
    created_docs.append(did)
    doc = wait_doc(client, emp, did)
    check("未知规格进入待确认", doc["status"] == "parsed" and doc["pending_count"] == 1,
          json.dumps(doc, ensure_ascii=False)[:200])

    r = client.get(f"{BASE}/api/ledger/pending", headers=admin)
    pendings = r.json().get("items") or []
    target = next((p for p in pendings if p["product_name"] == "新规格螺母"), None)
    check("待确认列表可查", r.status_code == 200 and target is not None, r.text[:150])

    r = client.post(f"{BASE}/api/ledger/pending/{target['id']}/resolve", headers=admin,
                    json={"action": "create", "unit": "千件"})
    check("待确认新建产品入库", r.status_code == 200, r.text[:150])
    r = client.get(f"{BASE}/api/products", headers=admin)
    new_products = [p for p in r.json() if p["name"] == "新规格螺母"]
    check("新产品已创建", len(new_products) == 1)
    r = client.get(f"{BASE}/api/ledger?start=2026-09-04&end=2026-09-04", headers=admin)
    check("条目已入台账", any(x["product_name"] == "新规格螺母" for x in r.json()["items"]), r.text[:200])

    text = "2026年9月4日 出货单\n客户：忽略测试公司\n杂项螺母 M77×7.7：出货 5 千件 单价 50 元 金额 250 元\n"
    files = {"file": ("smoke_忽略.txt", text.encode("utf-8"), "text/plain")}
    r = client.post(f"{BASE}/api/documents/upload", headers=emp, files=files)
    did = r.json().get("id")
    created_docs.append(did)
    doc = wait_doc(client, emp, did)
    check("规则提取出货待确认", doc["pending_count"] == 1 and doc["items"] == [],
          json.dumps(doc, ensure_ascii=False)[:200])
    r = client.get(f"{BASE}/api/ledger/pending", headers=admin)
    target = next((p for p in r.json()["items"] if p["product_name"] == "杂项螺母"), None)
    check("规则条目带单价金额客户", target and target["unit_price"] == 50 and target["amount"] == 250
          and target["customer"] == "忽略测试公司", json.dumps(target, ensure_ascii=False)[:200] if target else "not found")
    r = client.post(f"{BASE}/api/ledger/pending/{target['id']}/resolve", headers=admin, json={"action": "ignore"})
    check("忽略待确认条目", r.status_code == 200)
    r = client.get(f"{BASE}/api/ledger/pending", headers=admin)
    check("忽略后不再出现", all(p["product_name"] != "杂项螺母" for p in r.json()["items"]))

    # ── 单据管理 ──
    r = client.get(f"{BASE}/api/documents", headers=admin)
    check("单据列表(管理员)", r.status_code == 200 and isinstance(r.json(), list))
    r = client.get(f"{BASE}/api/documents/{created_docs[0]}", headers=emp)
    check("员工看自己单据详情", r.status_code == 200)
    check("员工不可见原始文本", r.json().get("raw_text") is None)
    r = client.get(f"{BASE}/api/documents/{created_docs[0]}/download", headers=emp)
    check("员工下载原件被拒", r.status_code == 403)

    # ── 手工记账 + 留痕 ──
    r = client.post(f"{BASE}/api/records", headers=admin, json={
        "biz_date": "2026-01-05", "revenue": 999.5, "cost": 400, "tx_count": 10,
        "payments": {"微信": 600, "现金": 399.5}, "category": "零售", "note": "冒烟测试"})
    check("手工记账", r.status_code == 201, r.text[:100])
    rid = r.json().get("id")
    cleanup_record_ids.append(rid)
    r = client.put(f"{BASE}/api/records/{rid}", headers=admin, json={"revenue": 1050, "category": "餐饮"})
    check("修改记录", r.status_code == 200 and len(r.json().get("changes", [])) == 2, r.text[:150])
    r = client.get(f"{BASE}/api/records/{rid}/edits", headers=admin)
    check("留痕可查", r.status_code == 200 and len(r.json()) == 1)
    r = client.post(f"{BASE}/api/records", headers=admin, json={"biz_date": "2026-01-05", "revenue": 1, "category": "不存在"})
    check("非法分类被拒", r.status_code == 400)
    r = client.get(f"{BASE}/api/records?start=2026-01-05&end=2026-01-05", headers=admin)
    check("明细记录查询", r.status_code == 200 and any(x["id"] == rid for x in r.json()))

    # ── 报表中心 ──
    r = client.get(f"{BASE}/api/reports/daily?start=2026-01-01&end=2026-12-31", headers=admin)
    check("日结单", r.status_code == 200 and "total" in r.json() and "days" in r.json())
    r = client.get(f"{BASE}/api/reports/category?start=2026-01-01&end=2026-12-31", headers=admin)
    check("分类排行", r.status_code == 200 and isinstance(r.json().get("items"), list))
    r = client.get(f"{BASE}/api/reports/compare?start=2026-09-01&end=2026-09-30", headers=admin)
    check("环比对比", r.status_code == 200 and "changes" in r.json())
    r = client.get(f"{BASE}/api/reports/export?start=2026-01-01&end=2026-12-31", headers=admin)
    check("Excel 导出", r.status_code == 200 and r.content[:2] == b"PK")

    # ── 看板（台账口径）──
    r = client.get(f"{BASE}/api/dashboard/overview", headers=admin)
    body = r.json()
    check("看板总览", r.status_code == 200 and all(k in body for k in
          ("summary", "prev_summary", "monthly_target", "daily", "monthly", "spec_stats", "recent_documents")))
    check("看板为台账口径", all(k in body["summary"] for k in
          ("today_production", "today_shipment", "ship_amount", "month_ship_amount")))
    check("看板含待处理统计", all(k in body["summary"] for k in
          ("pending_count", "failed_count", "pending_entry_count")))
    r = client.get(f"{BASE}/api/dashboard/overview", headers=admin, params={"product_id": 1})
    check("看板产品下钻", r.status_code == 200 and (r.json().get("product_filter") or {}).get("id") == 1)
    r = client.get(f"{BASE}/api/dashboard/overview", headers=admin, params={"product_id": 99999})
    check("看板下钻不存在产品404", r.status_code == 404)
    r = client.get(f"{BASE}/api/assistant/anomalies", headers=admin)
    alerts = r.json().get("alerts") or []
    check("异常预警为台账口径", r.status_code == 200 and isinstance(alerts, list)
          and all(a.get("type") in ("halt", "ship_drop", "stock") and a.get("message") for a in alerts))

    # ── 台账报表（L3b）──
    r = client.get(f"{BASE}/api/ledger/report", headers=admin,
                   params={"start": "2026-08-25", "end": "2030-12-31"})
    rep = r.json()
    check("台账报表结构", r.status_code == 200 and all(k in rep for k in ("range", "daily", "products", "summary"))
          and rep["range"]["start"] == "2026-08-25")
    # 端到端核对：报表期末结存 == 库存接口实时结存
    inv = {p["product_id"]: p["balance"] for p in client.get(f"{BASE}/api/ledger/inventory", headers=admin).json()}
    rep_close = {p["product_id"]: p["closing"] for p in rep["products"]}
    check("报表期末结存与库存一致", inv and all(abs(inv[k] - rep_close[k]) < 0.01 for k in inv if k in rep_close))
    # 日行滚动结存：最后一行每个产品的结存也要对上库存
    last_close = {}
    for row in rep["daily"]:
        last_close[row["product_id"]] = row["closing"]
    check("日报逐行滚动结存正确", last_close and all(abs(last_close[k] - inv[k]) < 0.01 for k in last_close if k in inv))
    r = client.get(f"{BASE}/api/ledger/report/export", headers=admin,
                   params={"start": "2026-08-25", "end": "2030-12-31"})
    check("台账报表Excel导出", r.status_code == 200 and r.content[:2] == b"PK"
          and "spreadsheet" in r.headers.get("content-type", ""))
    r = client.get(f"{BASE}/api/ledger/report", headers=emp)
    check("台账报表员工403", r.status_code == 403)
    r = client.get(f"{BASE}/api/reports/daily", headers=admin)
    check("旧财务报表接口仍可用", r.status_code == 200 and "days" in r.json())

    # ── 用户与审计 ──
    r = client.post(f"{BASE}/api/users", headers=admin, json={"username": "smoke_tmp", "password": "tmp123456", "role": "manager"})
    check("创建用户", r.status_code == 201, r.text[:100])
    uid = r.json().get("id")
    r = client.post(f"{BASE}/api/auth/login", json={"username": "smoke_tmp", "password": "tmp123456"})
    check("新用户可登录", r.status_code == 200)
    r = client.put(f"{BASE}/api/users/{uid}", headers=admin, json={"role": "employee", "is_active": False})
    check("更新用户", r.status_code == 200)
    r = client.post(f"{BASE}/api/auth/login", json={"username": "smoke_tmp", "password": "tmp123456"})
    check("停用账号登录被拒", r.status_code == 403)
    r = client.delete(f"{BASE}/api/users/{uid}", headers=admin)
    check("删除用户", r.status_code == 200)
    r = client.get(f"{BASE}/api/users/audit?limit=50", headers=admin)
    check("审计日志", r.status_code == 200 and len(r.json()) > 0)

    # ── 备份 ──
    r = client.post(f"{BASE}/api/backup", headers=admin)
    check("创建备份", r.status_code == 200, r.text[:100])
    bk = r.json().get("file")
    r = client.get(f"{BASE}/api/backup", headers=admin)
    check("备份列表", r.status_code == 200 and any(b["file"] == bk for b in r.json()))
    r = client.get(f"{BASE}/api/backup/download", headers=admin, params={"name": bk})
    check("备份下载", r.status_code == 200 and r.content[:2] == b"PK")
    r = client.delete(f"{BASE}/api/backup/{bk}", headers=admin)
    check("删除备份", r.status_code == 200)

    # ── 自动备份设置（保存校验后恢复原值，不改变用户配置） ──
    r = client.get(f"{BASE}/api/settings", headers=admin)
    orig_ab_on = r.json().get("auto_backup_enabled")
    orig_ab_time = r.json().get("auto_backup_time") or "23:30"
    r = client.put(f"{BASE}/api/settings", headers=admin, json={"auto_backup_enabled": True, "auto_backup_time": "23:58"})
    check("设置自动备份", r.status_code == 200 and r.json().get("auto_backup_enabled") is True
          and r.json().get("auto_backup_time") == "23:58", r.text[:150])
    r = client.put(f"{BASE}/api/settings", headers=admin, json={"auto_backup_time": "25:00"})
    check("非法备份时间被拒", r.status_code == 400)
    r = client.put(f"{BASE}/api/settings", headers=admin, json={"auto_backup_enabled": orig_ab_on, "auto_backup_time": orig_ab_time})
    check("恢复自动备份设置", r.status_code == 200 and r.json().get("auto_backup_time") == orig_ab_time)

    # ── mock LLM：AI 提取 / 流式问答 / 报告 ──
    mock = subprocess.Popen([sys.executable, str(Path(__file__).parent / "mock_llm.py")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(3)
        r = client.put(f"{BASE}/api/settings", headers=admin, json={
            "llm_api_base": "http://127.0.0.1:8001/v1", "llm_api_key": "smoke-key", "llm_model": "mock-model"})
        check("配置 mock LLM", r.status_code == 200 and r.json().get("llm_configured") is True, r.text[:150])
        r = client.post(f"{BASE}/api/settings/test-llm", headers=admin)
        check("测试连接", r.status_code == 200 and r.json().get("ok"))

        # LLM 提取路径：上传模板不命中的文档；新品名提取成功但不匹配产品 → 待确认
        llm_text = (
            "2026年9月5日 出货单\n"
            "智能螺母 M55×5.5 智能型：出货 20 千件 单价 80 元 金额 1600 元 客户：武汉标准件厂\n"
        )
        files = {"file": ("smoke_llm.txt", llm_text.encode("utf-8"), "text/plain")}
        r = client.post(f"{BASE}/api/documents/upload", headers=emp, files=files)
        did = r.json().get("id")
        created_docs.append(did)
        doc = wait_doc(client, emp, did)
        check("TXT 走 LLM 提取", doc["status"] == "parsed" and doc["pending_count"] == 1
              and (doc.get("pending") or [{}])[0].get("source") == "llm",
              json.dumps(doc, ensure_ascii=False)[:250])
        check("LLM 条目字段完整", doc.get("pending") and doc["pending"][0]["quantity"] == 20
              and doc["pending"][0]["unit_price"] == 80 and doc["pending"][0]["amount"] == 1600
              and doc["pending"][0]["customer"] == "武汉标准件厂",
              json.dumps(doc.get("pending"), ensure_ascii=False)[:200])

        # 会话管理：创建 → 两轮问答（多轮记忆）→ 回放 → 删除
        r = client.post(f"{BASE}/api/assistant/sessions", headers=admin)
        check("新建会话", r.status_code == 200 and r.json().get("id"), r.text[:100])
        sid = r.json()["id"]

        def chat_once(message, session_id):
            tools_, chunks_, done_, first_ = [], [], False, {}
            with client.stream("POST", f"{BASE}/api/assistant/chat", headers=admin,
                               json={"message": message, "session_id": session_id}, timeout=90) as resp_:
                for line in resp_.iter_lines():
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            done_ = True
                            continue
                        try:
                            obj = json.loads(payload)
                            if obj.get("session_id"):
                                first_ = obj
                            if obj.get("tool"):
                                tools_.append(obj["tool"])
                            if obj.get("delta"):
                                chunks_.append(obj["delta"])
                        except json.JSONDecodeError:
                            pass
                return resp_.status_code, tools_, "".join(chunks_), done_, first_

        code, tool_events, content, done, first = chat_once("本月出货量多少", sid)
        check("AI 问答流式", code == 200 and done and len(content) > 10, content[:80])
        check("智能体调用了工具", len(tool_events) > 0, f"tool_events={tool_events}")
        check("问答回传会话信息", first.get("session_id") == sid and first.get("title"), json.dumps(first, ensure_ascii=False))

        code2, _, content2, done2, _ = chat_once("那上周呢", sid)
        check("多轮记忆追问", code2 == 200 and done2 and len(content2) > 10, content2[:80])

        r = client.get(f"{BASE}/api/assistant/sessions/{sid}/messages", headers=admin)
        hist = r.json().get("messages", [])
        check("会话历史回放", r.status_code == 200 and sum(1 for m in hist if m["role"] == "user") == 2
              and any(m["role"] == "assistant" and not m.get("tool") for m in hist), json.dumps(hist, ensure_ascii=False)[:150])

        r = client.get(f"{BASE}/api/assistant/sessions", headers=admin)
        check("会话列表", r.status_code == 200 and any(s["id"] == sid for s in r.json()))
        r = client.delete(f"{BASE}/api/assistant/sessions/{sid}", headers=admin)
        check("删除会话", r.status_code == 200)
        r = client.get(f"{BASE}/api/assistant/sessions/{sid}/messages", headers=admin)
        check("删除后回放404", r.status_code == 404)

        # AI 报告（可视化：charts 结构由后端计算）
        anchor = data_anchor(client, admin)
        r = client.post(f"{BASE}/api/assistant/report", headers=admin, json={
            "report_type": "weekly", **({"anchor_date": anchor} if anchor else {})})
        body = r.json()
        charts = body.get("charts") or {}
        check("AI 周报生成", r.status_code == 200 and len(body.get("content", "")) > 30, r.text[:120])
        check("周报含可视化数据", r.status_code == 200 and len(charts.get("cards", [])) == 4
              and charts.get("trend", {}).get("dates") and charts.get("spec_rank") is not None
              and charts.get("inventory") is not None, json.dumps(charts, ensure_ascii=False)[:150])
        report_id = body.get("id")
        r = client.get(f"{BASE}/api/assistant/reports/{report_id}", headers=admin)
        check("报告详情含charts", r.status_code == 200 and r.json().get("charts", {}).get("cards"))
        r = client.get(f"{BASE}/api/assistant/reports", headers=admin)
        check("报告列表", r.status_code == 200 and any(x["id"] == report_id for x in r.json()))

        # ── 兜底 API：主服务商报错自动切备用 ──
        # 1) 主/备都配成 mock：备用可测通
        r = client.put(f"{BASE}/api/settings", headers=admin, json={
            "llm_backup_api_base": "http://127.0.0.1:8001/v1", "llm_backup_api_key": "smoke-key",
            "llm_backup_model": "mock-model"})
        check("配置备用 LLM", r.status_code == 200 and r.json().get("llm_backup_configured") is True, r.text[:150])
        r = client.post(f"{BASE}/api/settings/test-llm-backup", headers=admin)
        check("测试备用连接", r.status_code == 200 and r.json().get("ok"), r.text[:150])
        # 2) 主改成必挂地址（端口 9 无监听）：问答与报告应走备用自动恢复
        client.put(f"{BASE}/api/settings", headers=admin, json={"llm_api_base": "http://127.0.0.1:9/v1"})
        r = client.post(f"{BASE}/api/settings/test-llm", headers=admin)
        check("主挂时测试连接失败", r.status_code == 200 and r.json().get("ok") is False)
        code, tool_events, content, done, first = chat_once("今日库存结存多少", None)
        check("主挂时问答切备用", code == 200 and done and len(content) > 10, content[:80])
        fb_sid = first.get("session_id")
        if fb_sid:
            client.delete(f"{BASE}/api/assistant/sessions/{fb_sid}", headers=admin)
        r = client.post(f"{BASE}/api/assistant/report", headers=admin, json={
            "report_type": "weekly", **({"anchor_date": anchor} if anchor else {})})
        fb_report = r.json()
        check("主挂时报告切备用", r.status_code == 200 and len(fb_report.get("content", "")) > 30, r.text[:120])
        if fb_report.get("id"):
            client.delete(f"{BASE}/api/assistant/reports/{fb_report['id']}", headers=admin)
        client.put(f"{BASE}/api/settings", headers=admin, json={
            "llm_api_base": "http://127.0.0.1:8001/v1"})  # 恢复主为 mock，供 finally 清理
    finally:
        # 清理 LLM 配置（主 + 备用）
        client.put(f"{BASE}/api/settings", headers=admin, json={
            "llm_api_base": "", "llm_api_key": "", "llm_model": "",
            "llm_backup_api_base": "", "llm_backup_api_key": "", "llm_backup_model": ""})
        mock.terminate()

    # ── 清理测试数据 ──
    for rid in cleanup_record_ids:
        client.delete(f"{BASE}/api/records/{rid}", headers=admin)
    for did in created_docs:
        client.delete(f"{BASE}/api/documents/{did}", headers=admin)
    client.delete(f"{BASE}/api/templates/{tpl_id}", headers=admin)
    for p in client.get(f"{BASE}/api/products", headers=admin).json():
        if p["name"] in ("冒烟螺母", "新规格螺母"):
            client.delete(f"{BASE}/api/products/{p['id']}", headers=admin)
    if created_emp_id:
        client.delete(f"{BASE}/api/users/{created_emp_id}", headers=admin)
    r = client.get(f"{BASE}/api/settings", headers=admin)
    check("测试后 LLM 配置已清空", r.json().get("llm_configured") is False
          and r.json().get("llm_backup_configured") is False)

    # ── 汇总 ──
    failed = [x for x in results if not x[1]]
    print("\n" + "=" * 60)
    print(f"总计 {len(results)} 项，通过 {len(results) - len(failed)}，失败 {len(failed)}")
    for name, _, extra in failed:
        print(f"  ✗ {name}: {extra[:200]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
