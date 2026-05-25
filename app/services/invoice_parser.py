"""
納品書（写真・PDF）から Claude API で明細を読み取る
読み取り項目: 商品コード・数量・日付・納品元名のみ（商品名は読まない）
"""
from __future__ import annotations

import base64
import json
import re
from datetime import date
from typing import Optional

import anthropic

from app.config import _get_settings

EXTRACT_PROMPT = """この納品書・請求書画像から、次の4種類の情報だけを抽出してください。
商品名は読み取らないでください。

1. 各行の「商品コード」（JANコード・品番・バーコード番号）
2. 各行の「数量」（整数）
3. 「日付」（納品日・発行日。YYYY-MM-DD形式）
4. 「納品元名」（ディーラー名・会社名）

必ず次のJSON形式のみで返答（説明文不要）:
{
  "order_date": "2026-05-22",
  "dealer_name": "株式会社サンプル",
  "lines": [
    {"product_code": "4901001000001", "quantity": 3}
  ]
}
"""


def _parse_json_from_text(text: str) -> dict:
    text = text.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def parse_invoice_file(
    file_bytes: bytes,
    media_type: str,
) -> dict:
    settings = _get_settings()
    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY が設定されていません。")

    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    if media_type == "application/pdf":
        content = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64,
                },
            },
            {"type": "text", "text": EXTRACT_PROMPT},
        ]
    else:
        content = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            },
            {"type": "text", "text": EXTRACT_PROMPT},
        ]

    models = [settings.ANTHROPIC_MODEL, "claude-sonnet-4-5-20250929"]
    last_err: Optional[Exception] = None
    for model in dict.fromkeys(models):
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": content}],
            )
            raw = _parse_json_from_text(msg.content[0].text)
            return _normalize_result(raw)
        except Exception as e:
            last_err = e
    raise ValueError(f"納品書の読み取りに失敗しました: {last_err}")


def _normalize_result(raw: dict) -> dict:
    order_date = None
    if raw.get("order_date"):
        try:
            order_date = date.fromisoformat(str(raw["order_date"])[:10])
        except ValueError:
            pass

    lines = []
    for row in raw.get("lines") or []:
        code = str(row.get("product_code", "")).strip()
        if not code:
            continue
        try:
            qty = int(row.get("quantity", 0))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        lines.append({"product_code": code, "quantity": qty})

    return {
        "order_date": order_date,
        "dealer_name": (raw.get("dealer_name") or "").strip() or None,
        "lines": lines,
    }
