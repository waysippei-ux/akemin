"""
発注表 PDF — Claude で HTML 生成し WeasyPrint で PDF 化
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import anthropic

from app import crud
from app.config import BASE_DIR, _get_settings
from app.models import JST

logger = logging.getLogger(__name__)

PDF_DIR = (BASE_DIR / "data" / "order_pdfs").resolve()
FILENAME_RE = re.compile(r"^order_(\d+)_(\d{8})_(\d{6})\.pdf$")

ORDER_PDF_SYSTEM = """あなたはサロン向け発注表を作成するアシスタントです。
与えられたデータをもとに、印刷に適した日本語のHTMLを生成してください。
HTMLのみを返し、説明文は不要です。```html などのコードフェンスは使わないでください。"""


def pdf_path_for_filename(filename: str) -> Path:
    return PDF_DIR / filename


def _validate_filename_for_store(filename: str, store_id: int) -> bool:
    m = FILENAME_RE.match(filename)
    return bool(m and int(m.group(1)) == store_id)


def _sort_hierarchy(order_data: dict) -> dict:
    """ディーラー → カテゴリ → メーカーの順でキーをソート"""
    result: dict = {}
    for dealer in sorted(order_data.keys(), key=lambda x: (x == "（ディーラー未設定）", x)):
        result[dealer] = {}
        cats = order_data[dealer]
        for cat in sorted(cats.keys(), key=lambda x: (x == "（カテゴリ未設定）", x)):
            result[dealer][cat] = {}
            makers = cats[cat]
            for maker in sorted(makers.keys(), key=lambda x: (x == "（メーカー未設定）", x)):
                items = makers[maker]
                items.sort(key=lambda x: (not x.get("is_critical"), x.get("product_name", "")))
                result[dealer][cat][maker] = items
    return result


def _build_claude_user_prompt(store_name: str, today_jst: str, order_data: dict) -> str:
    return f"""
以下のデータで発注表一覧のHTMLを作成してください。
店舗名：{store_name}
作成日：{today_jst}

データ：{json.dumps(order_data, ensure_ascii=False, indent=2)}

要件：
・タイトルは「発注表一覧」
・大項目：ディーラー名（見出し）
・中項目：カテゴリ名（小見出し）
・小項目：メーカー名（グループ）
・各商品行：商品名/ブランド名 | 必要発注数（○本）
・is_criticalがtrueの商品は行末に赤文字で「至急発注が必要です」を追加
・印刷しやすいシンプルなデザイン
・CSSはstyleタグで埋め込む
・対象商品がない場合はその旨を明記する
"""


def _fallback_html(store_name: str, today_jst: str, order_data: dict) -> str:
    """Claude 未設定時の簡易 HTML"""
    parts = [
        "<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>",
        "<style>",
        "body{font-family:'Hiragino Sans',sans-serif;font-size:12px;padding:24px;}",
        "h1{font-size:20px;} h2{font-size:16px;margin-top:20px;border-bottom:1px solid #ccc;}",
        "h3{font-size:14px;margin-top:12px;color:#444;} h4{font-size:13px;margin:8px 0;}",
        "table{width:100%;border-collapse:collapse;margin:8px 0 16px;}",
        "th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;}",
        ".crit{color:#c00;font-weight:bold;}",
        "</style></head><body>",
        f"<h1>発注表一覧</h1>",
        f"<p>店舗：{store_name}　作成日：{today_jst}</p>",
    ]
    if not order_data:
        parts.append("<p>黄アラート以下の対象商品はありません。</p>")
    for dealer, cats in order_data.items():
        parts.append(f"<h2>{dealer}</h2>")
        for cat, makers in cats.items():
            parts.append(f"<h3>{cat}</h3>")
            for maker, items in makers.items():
                parts.append(f"<h4>{maker}</h4>")
                parts.append(
                    "<table><thead><tr><th>商品</th><th>ブランド</th><th>必要数</th><th>備考</th></tr></thead><tbody>"
                )
                for it in items:
                    crit = (
                        '<span class="crit">至急発注が必要です</span>'
                        if it.get("is_critical")
                        else ""
                    )
                    brand = it.get("brand_name") or "—"
                    unit = it.get("unit") or "本"
                    parts.append(
                        f"<tr><td>{it['product_name']}</td><td>{brand}</td>"
                        f"<td>{it['needed']}{unit}</td><td>{crit}</td></tr>"
                    )
                parts.append("</tbody></table>")
    parts.append("</body></html>")
    return "".join(parts)


def _generate_html_with_claude(store_name: str, today_jst: str, order_data: dict) -> str:
    settings = _get_settings()
    api_key = settings.ANTHROPIC_API_KEY
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY 未設定 — 発注表はテンプレート HTML を使用")
        return _fallback_html(store_name, today_jst, order_data)

    client = anthropic.Anthropic(api_key=api_key)
    user_prompt = _build_claude_user_prompt(store_name, today_jst, order_data)
    message = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=16000,
        system=ORDER_PDF_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = message.content[0].text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    if "<html" not in text.lower():
        text = _fallback_html(store_name, today_jst, order_data)
    return text


def generate_order_pdf(db, store_id: int) -> tuple[str, str]:
    """
    発注表 PDF を生成し (pdf_url, filename) を返す。
    pdf_url は認証付きダウンロード API へのパス。
    """
    store_name, today_jst, order_data = crud.build_order_pdf_hierarchy(db, store_id)
    order_data = _sort_hierarchy(order_data)

    html_content = _generate_html_with_claude(store_name, today_jst, order_data)

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(JST)
    filename = f"order_{store_id}_{now.strftime('%Y%m%d')}_{now.strftime('%H%M%S')}.pdf"
    pdf_path = pdf_path_for_filename(filename)

    try:
        from weasyprint import HTML
    except OSError as e:
        raise RuntimeError(
            "WeasyPrint のシステムライブラリが不足しています。"
            " https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation "
            "を参照してインストールしてください。"
        ) from e

    HTML(string=html_content, base_url=str(BASE_DIR)).write_pdf(str(pdf_path))

    pdf_url = f"/api/orders/order-pdf/download/{filename}?store_id={store_id}"
    return pdf_url, filename
