"""
棚補充・使用登録（商品検索・スキャン・一括）
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import crud
from app.models import Inventory, InventoryAction, User
from app.schemas import (
    InventoryScanResponse,
    ProductCreate,
    StockBulkLineIn,
    StockBulkParseLineOut,
    StockBulkParseResult,
    StockBulkRegisterRequest,
    StockLookupOut,
    StockRegisterRequest,
    StockRegisterWithProductRequest,
)


def _inventory_qty(db: Session, store_id: int, product_id: int) -> int:
    inv = (
        db.query(Inventory)
        .filter(Inventory.store_id == store_id, Inventory.product_id == product_id)
        .first()
    )
    return inv.quantity if inv else 0


def lookup_stock_product(db: Session, store_id: int, code: str) -> StockLookupOut:
    scan_code = (code or "").strip()
    product = crud.resolve_product_for_scan(db, scan_code)
    if not product:
        return StockLookupOut(code=scan_code, found=False)
    return StockLookupOut(
        code=scan_code,
        found=True,
        product_id=product.id,
        product_name=product.name,
        barcode=product.barcode,
        unit=product.unit,
        quantity=_inventory_qty(db, store_id, product.id),
        category_id=product.category_id,
    )


def _apply_stock_by_product(
    db: Session,
    user: User,
    store_id: int,
    product_id: int,
    action: InventoryAction,
    quantity: int,
    recorded_at=None,
) -> InventoryScanResponse:
    product = crud.get_product_by_id(db, product_id)
    if not product:
        raise ValueError("商品が見つかりません。")

    inv = crud.get_or_create_inventory(db, store_id, product.id)

    if action == InventoryAction.USE:
        if inv.quantity < quantity:
            raise ValueError(
                f"在庫が足りません（現在: {inv.quantity}{product.unit}）"
            )
        inv.quantity -= quantity
        action_label = "使用"
    else:
        inv.quantity += quantity
        action_label = "補充"

    setting = crud.get_settings_map(db, store_id).get(product.id)
    warning, critical = crud.resolve_thresholds(product, setting)
    level = crud.calc_stock_level(inv.quantity, warning, critical)

    from app.models import InventoryLog

    log = InventoryLog(
        store_id=store_id,
        product_id=product.id,
        user_id=user.id,
        action=action,
        quantity_change=quantity,
        quantity_after=inv.quantity,
    )
    if recorded_at:
        log.created_at = recorded_at
    db.add(log)
    db.commit()
    db.refresh(inv)

    return InventoryScanResponse(
        product_name=product.name,
        action=action,
        quantity_change=quantity,
        quantity_after=inv.quantity,
        stock_level=level,
        message=f"{product.name} を{action_label}しました（残り {inv.quantity}{product.unit}）",
    )


def register_stock(
    db: Session, user: User, data: StockRegisterRequest
) -> InventoryScanResponse:
    return _apply_stock_by_product(
        db,
        user,
        data.store_id,
        data.product_id,
        data.action,
        data.quantity,
        data.recorded_at,
    )


def register_stock_with_new_product(
    db: Session, user: User, data: StockRegisterWithProductRequest
) -> InventoryScanResponse:
    if data.product.critical_threshold > data.product.warning_threshold:
        raise ValueError("危険閾値は注意閾値以下にしてください。")
    product = crud.create_product(db, data.product)
    return _apply_stock_by_product(
        db,
        user,
        data.store_id,
        product.id,
        data.action,
        data.quantity,
        data.recorded_at,
    )


def bulk_register_stock(
    db: Session, user: User, data: StockBulkRegisterRequest
) -> dict:
    if not data.lines:
        raise ValueError("登録する行がありません。")
    messages: list[str] = []
    for line in data.lines:
        res = _apply_stock_by_product(
            db,
            user,
            data.store_id,
            line.product_id,
            data.action,
            line.quantity,
            line.recorded_at,
        )
        messages.append(res.message)
    return {"count": len(data.lines), "messages": messages}


def build_stock_bulk_parse_result(
    db: Session,
    store_id: int,
    parsed: dict,
    dealer_id: int | None = None,
) -> StockBulkParseResult:
    """納品書OCR結果をマスタ商品と照合"""
    lines_out: list[StockBulkParseLineOut] = []
    unmatched = 0

    for ln in parsed.get("lines") or []:
        code = str(ln.get("product_code") or "").strip()
        try:
            qty = int(ln.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1
        if qty < 1:
            qty = 1

        product = crud.resolve_product_for_scan(db, code)
        if not product:
            product = crud.match_product_for_invoice(db, code, dealer_id)

        if product:
            lines_out.append(
                StockBulkParseLineOut(
                    product_code=code,
                    quantity=qty,
                    matched=True,
                    product_id=product.id,
                    product_name=product.name,
                    unit=product.unit,
                    current_quantity=_inventory_qty(db, store_id, product.id),
                )
            )
        else:
            unmatched += 1
            lines_out.append(
                StockBulkParseLineOut(
                    product_code=code,
                    quantity=qty,
                    matched=False,
                )
            )

    note = None
    if unmatched:
        note = (
            f"{unmatched} 件はマスタと一致しませんでした。"
            "JANコード・バーコード・納品コードをご確認ください。"
        )
    order_date = parsed.get("order_date")
    if order_date:
        note = (note or "") + f" 読み取り日付: {order_date}"

    return StockBulkParseResult(lines=lines_out, note=note or None)
