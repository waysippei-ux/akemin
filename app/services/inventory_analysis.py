"""
Anthropic Claude API を使った在庫分析

在庫データと直近の使用ログをもとに、
「そろそろ発注が必要」などの日本語アドバイスを生成する。
"""
from __future__ import annotations

import json
import logging

import anthropic
from sqlalchemy.orm import Session

from app import crud
from app.config import _get_settings

logger = logging.getLogger(__name__)

# .env のモデルが使えない場合の代替（Sonnet 4.5）
MODEL_FALLBACK = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = """あなたは美容室のカラー材在庫管理を支援するアシスタントです。
スタッフ向けに、在庫データを分析して発注のアドバイスを日本語で書いてください。

ルール:
- 敬体（です・ます調）で、簡潔に3〜6文程度
- 赤（red）の商品を最優先で言及する
- 黄（yellow）の商品も「そろそろ発注を検討」と伝える
- 直近ログから使用ペースが速い商品があれば触れる
- 発注は手動であることを踏まえ、押し付けがましくしない
- 箇条書きでも段落でもよいが、読みやすく
- データにない商品名は出さない
"""


def _build_user_prompt(context: dict) -> str:
    """Claude に渡すユーザーメッセージを組み立てる"""
    inventory = context.get("inventory", [])
    logs = context.get("recent_logs", [])
    store_name = context.get("store_name", "店舗")
    category_name = context.get("category_name", "")
    scope = f"{store_name}" + (f" / {category_name}" if category_name else "")

    low_stock = [i for i in inventory if i["level"] in ("red", "yellow")]
    low_stock_text = (
        "\n".join(
            f"- {i['name']}: 残り{i['quantity']}{i['unit']}（{i['level']}）"
            for i in low_stock
        )
        if low_stock
        else "（在庫不足の商品はありません）"
    )

    log_text = (
        "\n".join(
            f"- {l['at'][:10]} {l['product']}: {l['action']} {l['change']} → 残{l['after']}"
            for l in logs[:15]
        )
        if logs
        else "（直近の変動ログはありません）"
    )

    return f"""以下は「{scope}」の在庫データです。発注のアドバイスをお願いします。

【在庫一覧（level: green=十分, yellow=そろそろ要発注, red=至急）】
{json.dumps(inventory, ensure_ascii=False, indent=2)}

【要注目の在庫】
{low_stock_text}

【直近7日の使用・補充ログ（最大15件）】
{log_text}
"""


def _call_claude(api_key: str, model: str, user_prompt: str) -> str:
    """Claude API を呼び出してテキストを返す"""
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text.strip()


def analyze_inventory(
    db: Session, store_id: int, category_id: int | None = None
) -> str:
    """
    店舗の在庫を分析し、日本語のアドバイス文を返す

    APIキー未設定やAPIエラー時は、ルールベースの簡易メッセージにフォールバックする。
    """
    settings = _get_settings()
    context = crud.build_analysis_context(db, store_id, category_id=category_id)
    user_prompt = _build_user_prompt(context)

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY が未設定です")
        return _fallback_advice(context, reason="APIキーが設定されていません")

    # .env のモデル → 利用不可なら代替モデルを試す
    models_to_try = []
    for m in (settings.ANTHROPIC_MODEL, MODEL_FALLBACK):
        if m and m not in models_to_try:
            models_to_try.append(m)

    last_error: Exception | None = None
    for model in models_to_try:
        try:
            return _call_claude(settings.ANTHROPIC_API_KEY, model, user_prompt)
        except anthropic.NotFoundError as e:
            logger.warning("モデル %s は利用不可: %s", model, e)
            last_error = e
        except anthropic.AuthenticationError as e:
            logger.error("Anthropic 認証エラー: %s", e)
            return _fallback_advice(context, reason="APIキーが無効です")
        except TypeError as e:
            # anthropic 0.39 + httpx 0.28 の proxies 非互換など
            logger.error("Anthropic SDK の互換性エラー: %s", e)
            return _fallback_advice(
                context,
                reason="anthropic パッケージを更新してください（pip install -U 'anthropic>=0.45.0'）",
            )
        except Exception as e:
            logger.exception("Claude API 呼び出し失敗 (model=%s)", model)
            last_error = e

    reason = f"APIエラー: {last_error}" if last_error else "APIに接続できませんでした"
    return _fallback_advice(context, reason=reason)


def _fallback_advice(context: dict, reason: str = "") -> str:
    """APIが使えないときの簡易アドバイス（ルールベース）"""
    store_name = context.get("store_name", "店舗")
    inventory = context.get("inventory", [])

    red = [i for i in inventory if i["level"] == "red"]
    yellow = [i for i in inventory if i["level"] == "yellow"]

    lines = [f"【{store_name}】の在庫状況です。"]

    if red:
        names = "、".join(f"「{i['name']}」（残り{i['quantity']}{i['unit']}）" for i in red)
        lines.append(f"{names}は在庫が少なく、至急の発注をおすすめします。")

    if yellow:
        names = "、".join(f"「{i['name']}」" for i in yellow)
        lines.append(f"{names}はそろそろ切れそうです。今週中の発注を検討してください。")

    if not red and not yellow:
        lines.append("現時点で特に危険な在庫はありません。引き続きバーコードでの入出庫をお願いします。")

    lines.append(f"（Claude API に接続できないため、簡易分析を表示しています。{reason}）")
    return "\n".join(lines)
