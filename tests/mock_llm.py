"""测试用 mock 大模型服务：模拟 OpenAI 兼容 /chat/completions 接口（支持流式 + 提取/报告/问答三种行为）。"""

import asyncio
import json
import re

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()


TYPE_MAP = {"生产": "production", "出货": "shipment", "报废": "scrap", "退货": "return", "结存": "initial"}


def fake_extract(text: str) -> str:
    """按关键词从文本里抓规格条目，返回工厂台账 items JSON。"""
    date_m = re.search(r"20\d{2}-\d{1,2}-\d{1,2}", text)
    the_date = date_m.group(0) if date_m else "2026-09-03"
    items = []
    for line in text.splitlines():
        spec_m = re.search(r"([\u4e00-\u9fa5]{1,12})\s+(M\d+(?:[×x]\d+(?:\.\d+)?)?\S*)", line)
        typed = list(re.finditer(r"(生产|出货|报废|退货|结存)[：:]?\s*([\d.]+)\s*(千件|件)?", line))
        if not typed:
            continue
        price_m = re.search(r"单价[：:]?\s*([\d.]+)", line)
        amount_m = re.search(r"金额[：:]?\s*([\d.]+)", line)
        cust_m = re.search(r"客户[：:]?\s*([\u4e00-\u9fa5]+)", line)
        for tm in typed:
            items.append({
                "date": the_date,
                "product_name": spec_m.group(1) if spec_m else "",
                "spec": spec_m.group(2) if spec_m else "",
                "entry_type": TYPE_MAP[tm.group(1)],
                "quantity": float(tm.group(2)),
                "unit": tm.group(3) or None,
                "unit_price": float(price_m.group(1)) if price_m else None,
                "amount": float(amount_m.group(1)) if amount_m else None,
                "customer": cust_m.group(1) if cust_m else None,
                "confidence": 0.9,
                "evidence": line[:80],
            })
    return json.dumps({"items": items}, ensure_ascii=False)


@app.post("/v1/chat/completions")
async def completions(request: Request):
    body = await request.json()
    stream = body.get("stream", False)

    msgs = body.get("messages", [])
    last_user = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "")
    last_msg = msgs[-1] if msgs else {}
    first_content = msgs[0].get("content", "") if msgs else ""

    # ── 智能体模式：带 tools 的请求 → 返回 tool_calls 或最终回答 ──
    if body.get("tools"):
        if last_msg.get("role") == "tool":
            answer = "根据工具查询结果：本月（2026-09）产量合计 415 千件，出货量合计 165 千件，出货金额 17,600 元，库存结存正常。"
        else:
            answer = None
        tool_calls = None
        if answer is None:
            tool_calls = [{
                "id": "call_smoke_1", "type": "function", "index": 0,
                "function": {"name": "query_daily",
                             "arguments": json.dumps({"start": "2026-09-01", "end": "2026-09-30"})},
            }]
    elif "工厂台账数据提取助手" in last_user or "工厂经营记录文本" in last_user:
        answer = fake_extract(last_user)
        tool_calls = None
    elif "报告" in first_content or "总体概况" in last_user:
        answer = (
            "总体概况：本期共 4 天有台账数据，产量合计 415 千件，出货量合计 165 千件，"
            "出货金额 26,400 元，日均出货约 41 千件。\n\n"
            "经营亮点：9月1日出货 80 千件创本期新高，主要来自武汉标准件厂订单。\n\n"
            "存在问题：M8×1.25 规格报废 0.5 千件，需关注模具磨损。\n\n"
            "改进建议：1) 保持生产日报上传习惯，便于持续跟踪；2) 复核 M8 报废原因；"
            "3) 关注低库存规格及时补产。"
        )
        tool_calls = None
    else:
        answer = "根据系统内的台账数据：本月（2026-09）产量 415 千件，出货量 165 千件，出货金额 17,600 元；各规格库存结存正常，无低于预警线的产品。如需更细的分析可以继续问我。"
        tool_calls = None

    if tool_calls and not stream:
        return {
            "id": "mock", "object": "chat.completion", "model": body.get("model"),
            "choices": [{"index": 0, "finish_reason": "tool_calls",
                         "message": {"role": "assistant", "content": None, "tool_calls": [
                             {k: v for k, v in tc.items() if k != "index"} for tc in tool_calls]}}],
        }
    if not stream:
        return {
            "id": "mock", "object": "chat.completion", "model": body.get("model"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": answer}}],
        }

    async def gen():
        if tool_calls:
            chunk = {
                "id": "mock", "object": "chat.completion.chunk", "model": body.get("model"),
                "choices": [{"index": 0, "finish_reason": None,
                             "delta": {"role": "assistant", "tool_calls": [
                                 {k: v for k, v in tc.items() if k != "index"} for tc in tool_calls]}}],
            }
            yield "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"
            return
        step = 12
        for i in range(0, len(answer), step):
            chunk = {
                "id": "mock", "object": "chat.completion.chunk", "model": body.get("model"),
                "choices": [{"index": 0, "finish_reason": None,
                             "delta": {"content": answer[i : i + step]}}],
            }
            yield "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"
            await asyncio.sleep(0.03)
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
