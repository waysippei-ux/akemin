"""
アケミンAI — 在庫データをもとに Claude と会話
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import anthropic
from sqlalchemy.orm import Session, joinedload

from app import crud
from app.config import _get_settings
from app.crud_store_settings import get_settings_map, resolve_standard_stock, resolve_thresholds
from app.models import Inventory, InventoryAction, InventoryLog, JST, Product
from app.services.inventory_analysis import MODEL_FALLBACK

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """あなたは美容サロン「{store_name}」の在庫管理AIアシスタント「アケミンAI」です。
店舗スタッフの質問に対して、在庫データをもとに具体的で実用的なアドバイスをしてください。
返答は日本語で、親しみやすく丁寧な口調でお願いします。
数字や商品名は具体的に挙げてください。"""


def _log_line(log: InventoryLog) -> str:
    product = log.product
    name = product.name if product else "（商品不明）"
    brand = ""
    if product and product.brand:
        brand = product.brand.name
    brand_part = f"（{brand}）" if brand else ""
    dt = log.created_at
    if dt and dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    date_str = dt.astimezone(JST).strftime("%m/%d") if dt else ""
    qty = int(log.quantity_change or 0)
    sign = "+" if log.action == InventoryAction.RESTOCK else "-"
    return f"・{name}{brand_part}: {sign}{qty}本 {date_str}"


def _inventory_line(db: Session, store_id: int, inv: Inventory) -> str:
    product = inv.product
    if not product:
        return ""
    settings_map = get_settings_map(db, store_id)
    std = resolve_standard_stock(product, settings_map.get(product.id))
    warning, critical = resolve_thresholds(product, settings_map.get(product.id))
    qty = int(inv.quantity or 0)
    level = ""
    if qty <= critical:
        level = "【至急】"
    elif qty <= warning:
        level = "【要発注】"
    std_label = std if std else "未設定"
    return f"・{product.name}: 現在{qty}本（標準{std_label}本）{level}"


def build_chat_context(db: Session, store_id: int) -> dict:
    """過去30日の補充・使用と現在庫サマリー"""
    store = crud.get_store(db, store_id)
    store_name = store.name if store else "不明"

    since = datetime.now(JST) - timedelta(days=30)

    def _logs_for(action: InventoryAction, limit: int = 30) -> list[str]:
        rows = (
            db.query(InventoryLog)
            .options(
                joinedload(InventoryLog.product).joinedload(Product.brand),
            )
            .filter(
                InventoryLog.store_id == store_id,
                InventoryLog.action == action,
                InventoryLog.created_at >= since,
            )
            .order_by(InventoryLog.created_at.desc(), InventoryLog.id.desc())
            .limit(limit)
            .all()
        )
        return [_log_line(log) for log in rows]

    replenish_summary = "\n".join(_logs_for(InventoryAction.RESTOCK))
    consume_summary = "\n".join(_logs_for(InventoryAction.USE))

    inv_rows = (
        db.query(Inventory)
        .options(
            joinedload(Inventory.product).joinedload(Product.brand),
        )
        .filter(
            Inventory.store_id == store_id,
            Inventory.is_active.is_(True),
        )
        .order_by(Inventory.quantity.asc())
        .limit(80)
        .all()
    )
    inventory_lines = [_inventory_line(db, store_id, inv) for inv in inv_rows]
    inventory_lines = [ln for ln in inventory_lines if ln]

    return {
        "store_name": store_name,
        "replenish_summary": replenish_summary or "記録なし",
        "consume_summary": consume_summary or "記録なし",
        "inventory_summary": "\n".join(inventory_lines[:50]) or "記録なし",
        "today": datetime.now(JST).strftime("%Y/%m/%d"),
    }


def _call_claude(api_key: str, model: str, system: str, user_prompt: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1000,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text.strip()


def chat_with_akemin(db: Session, store_id: int, message: str) -> str:
    """スタッフの質問に対してアケミンAIが返答"""
    message = (message or "").strip()
    if not message:
        raise ValueError("メッセージを入力してください。")

    ctx = build_chat_context(db, store_id)
    settings = _get_settings()

    user_prompt = f"""【店舗】{ctx["store_name"]}
【質問日】{ctx["today"]}

【過去30日の補充履歴】
{ctx["replenish_summary"]}

【過去30日の使用履歴】
{ctx["consume_summary"]}

【現在の在庫状況（棚に並んでいる商品）】
{ctx["inventory_summary"]}

【質問】
{message}
"""

    if not settings.ANTHROPIC_API_KEY:
        return (
            "申し訳ありません。AI機能のAPIキーが設定されていないため、"
            "いまはお答えできません。管理者にお問い合わせください。"
        )

    system = SYSTEM_TEMPLATE.format(store_name=ctx["store_name"])
    models_to_try = []
    for m in (settings.ANTHROPIC_MODEL, MODEL_FALLBACK):
        if m and m not in models_to_try:
            models_to_try.append(m)

    last_error: Exception | None = None
    for model in models_to_try:
        try:
            return _call_claude(settings.ANTHROPIC_API_KEY, model, system, user_prompt)
        except anthropic.NotFoundError as e:
            logger.warning("モデル %s は利用不可: %s", model, e)
            last_error = e
        except anthropic.AuthenticationError:
            return "APIキーが無効です。管理者にご確認ください。"
        except Exception as e:
            logger.exception("アケミンAI API エラー")
            last_error = e

    logger.error("アケミンAI: 全モデル失敗 %s", last_error)
    return "申し訳ありません。AIの応答を取得できませんでした。しばらくしてからもう一度お試しください。"
