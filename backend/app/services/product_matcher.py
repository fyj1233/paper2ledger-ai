"""产品匹配：把提取出的自由文本（品名+规格）关联到产品主数据。

匹配级别：① 名称+规格归一化全等 → ② 合并串全等（LLM 把名称规格合在一起）→
③ 规格全等 + 品名互相包含 → ④ 规格互相包含（限长规格，防误配）。
全部失败返回 None，由调用方落「待确认」。
"""

import re
import unicodedata

from app.models import Product

# 规格核心：M6 / M8×1.25 / M12x1.75 等（× x X * 分隔）
SPEC_CORE_RE = re.compile(r"[Mm]\s?\d+(?:\s?[×xX*·]\s?\d+(?:\.\d+)?)?")


def _norm(s: str) -> str:
    """归一化：全角→半角、小写、×xX*→x、去掉全部空白。"""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    for ch in ("×", "Ｘ", "✕", "*", "·"):
        s = s.replace(ch, "x")
    return re.sub(r"\s+", "", s).lower()


def build_keys(product: Product) -> tuple[str, str, str]:
    return _norm(product.name), _norm(product.spec), _norm(product.name + product.spec)


def match_product(products: list[Product], name: str, spec: str) -> Product | None:
    n_name, n_spec = _norm(name or ""), _norm(spec or "")
    if not n_name and not n_spec:
        return None
    full = _norm((name or "") + (spec or ""))

    # ① 名称+规格归一化全等
    for p in products:
        pn, ps, _ = build_keys(p)
        if pn == n_name and ps == n_spec:
            return p
    # ② 合并串全等（提取端没拆名称/规格）
    if full:
        for p in products:
            if build_keys(p)[2] == full:
                return p
    # ③ 规格全等 + 品名互相包含（规格是更强的键）
    if n_spec:
        for p in products:
            pn, ps, _ = build_keys(p)
            if ps == n_spec and (not n_name or not pn or n_name in pn or pn in n_name):
                return p
    # ④ 规格互相包含（前缀/超集），规格太短不参与，防止 M8 误配 M80
    if n_spec and len(n_spec) >= 5:
        for p in products:
            pn, ps, _ = build_keys(p)
            if ps and len(ps) >= 5 and (ps in n_spec or n_spec in ps):
                if not n_name or not pn or n_name in pn or pn in n_name:
                    return p
    return None
