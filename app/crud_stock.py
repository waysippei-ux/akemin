"""
棚補充・使用登録（商品検索・スキャン・一括）
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import crud, crud_store_settings
from app.models import Inventory, InventoryAction, User
from app.schemas import (
    InventoryScanResponse,
    ProductCreate,
    StockBulkLineIn,
    StockBulkParseLineOut,
    StockBulkParseResult,
    StockBulkRegisterRequest,
    StockConsumeRequest,
    StockLookupOut,
    StockRegisterRequest,
    StockRegisterWithProductRequest,
    StockReplenishRequest,
)


def _inventory_row(db: Session, store_id: int, product_id: int) -> Inventory | None:
    return crud.get_inventory_row(db, store_id, product_id)


def lookup_stock_product(db: Session, store_id: int, code: str) -> StockLookupOut:
    scan_code = (code or "").strip()
    product = crud.resolve_product_for_scan(db, scan_code)
    if not product:
        return StockLookupOut(code=scan_code, found=False)
    inv = _inventory_row(db, store_id, product.id)
    on_shelf = inv is not None and inv.is_active
    return StockLookupOut(
        code=scan_code,
        found=True,
        product_id=product.id,
        product_name=product.name,
        barcode=product.barcode,
        unit=product.unit,
        quantity=inv.quantity if inv else 0,
        category_id=product.category_id,
        is_on_shelf=on_shelf,
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
    crud.require_store_id_for_stock(store_id)
    product = crud.get_product_by_id(db, product_id)
    if not product:
        raise ValueError("商品が見つかりません。")

    if action == InventoryAction.USE:
        inv = crud.assert_product_on_shelf_for_use(db, store_id, product.id)
        crud.assert_use_quantity_allowed(inv.quantity, quantity, product.unit)
        inv.quantity -= quantity
        action_label = "使用"
    else:
        inv = crud.activate_inventory_at_store(db, store_id, product.id, commit=False)
        inv.quantity += quantity
        action_label = "補充"

    setting = crud_store_settings.get_settings_map(db, store_id).get(product.id)
    warning, critical = crud_store_settings.resolve_thresholds(product, setting)
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


def get_product_quantity_at_store(
    db: Session, store_id: int, product_id: int
) -> tuple[int, str, bool]:
    """店舗×商品の現在庫（単位・棚配置フラグ付き）"""
    crud.require_store_id_for_stock(store_id)
    product = crud.get_product_by_id(db, product_id)
    if not product:
        raise ValueError("商品が見つかりません。")
    inv = _inventory_row(db, store_id, product_id)
    qty = inv.quantity if inv else 0
    on_shelf = inv is not None and inv.is_active
    return qty, product.unit or "本", on_shelf


def register_stock(
    db: Session, user: User, data: StockRegisterRequest
) -> InventoryScanResponse:
    crud.require_store_id_for_stock(data.store_id)
    return _apply_stock_by_product(
        db,
        user,
        data.store_id,
        data.product_id,
        data.action,
        data.quantity,
        data.recorded_at,
    )


def replenish_stock(
    db: Session, user: User, data: StockReplenishRequest
) -> InventoryScanResponse:
    crud.require_store_id_for_stock(data.store_id)
    return _apply_stock_by_product(
        db,
        user,
        data.store_id,
        data.product_id,
        InventoryAction.RESTOCK,
        data.quantity,
        data.recorded_at,
    )


def consume_stock(
    db: Session, user: User, data: StockConsumeRequest
) -> InventoryScanResponse:
    crud.require_store_id_for_stock(data.store_id)
    return _apply_stock_by_product(
        db,
        user,
        data.store_id,
        data.product_id,
        InventoryAction.USE,
        data.quantity,
        data.recorded_at,
    )


def register_stock_with_new_product(
    db: Session, user: User, data: StockRegisterWithProductRequest
) -> InventoryScanResponse:
    crud.require_store_id_for_stock(data.store_id)
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
    crud.require_store_id_for_stock(data.store_id)
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
            inv = _inventory_row(db, store_id, product.id)
            lines_out.append(
                StockBulkParseLineOut(
                    product_code=code,
                    quantity=qty,
                    matched=True,
                    product_id=product.id,
                    product_name=product.name,
                    unit=product.unit,
                    current_quantity=inv.quantity if inv else 0,
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
