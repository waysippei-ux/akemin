"""
棚補充・使用 — 画面ルート・API
"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, crud_masters, crud_stock
from app.auth import check_store_access, get_current_user
from app.config import BASE_DIR
from app.database import get_db
from app.models import User
from app.schemas import (
    CategoryOut,
    DealerOut,
    InventoryItemOut,
    InventoryScanResponse,
    MakerOut,
    StockBulkParseResult,
    StockBulkRegisterRequest,
    StockLookupOut,
    StockQuantityOut,
    StockRegisterRequest,
    StockRegisterWithProductRequest,
    StoreOut,
)
from app.services.invoice_parser import parse_invoice_file

templates = Jinja2Templates(directory=str((BASE_DIR / "templates").resolve()))

# HTML 画面（/stock/replenish, /stock/consume）
pages_router = APIRouter(tags=["棚補充・使用 画面"])

# JSON API（/api/stock/...）
router = APIRouter()


def _stock_page_context(
    db: Session, stock_mode: str, store_id: Optional[int] = None
) -> dict[str, Any]:
    """店舗・マスタ・初期在庫をテンプレートへ渡す（SSR + JS 初期化）"""
    stores = [
        StoreOut.model_validate(s).model_dump(mode="json")
        for s in crud.get_stores(db, active_only=True)
    ]
    categories = [
        CategoryOut.model_validate(c).model_dump(mode="json")
        for c in crud_masters.get_categories(db, active_only=True)
    ]
    makers = [
        MakerOut.model_validate(m).model_dump(mode="json")
        for m in crud_masters.get_makers(db, active_only=True)
    ]
    dealers = [
        DealerOut.model_validate(d).model_dump(mode="json")
        for d in crud_masters.get_dealers(db, active_only=True)
    ]
    store_ids = {s["id"] for s in stores}
    default_store_id: Optional[int] = None
    if store_id and store_id in store_ids:
        default_store_id = store_id
    elif stores:
        default_store_id = stores[0]["id"]

    active_only = stock_mode != "replenish"
    inventory_items: list[dict[str, Any]] = []
    if default_store_id is not None:
        inventory_items = [
            InventoryItemOut.model_validate(item).model_dump(mode="json")
            for item in crud.get_inventory_list(
                db, default_store_id, active_only=active_only
            )
        ]

    page_data = {
        "stores": stores,
        "categories": categories,
        "makers": makers,
        "dealers": dealers,
        "inventory": inventory_items,
        "default_store_id": default_store_id,
    }
    return {
        "stock_mode": stock_mode,
        "stores": stores,
        "categories": categories,
        "makers": makers,
        "dealers": dealers,
        "default_store_id": default_store_id,
        "stock_page_data_json": json.dumps(page_data, ensure_ascii=False),
    }


@pages_router.get("/stock/replenish")
def stock_replenish_page(
    request: Request,
    db: Session = Depends(get_db),
    store_id: Optional[int] = Query(None, gt=0),
):
    return templates.TemplateResponse(
        request, "stock.html", _stock_page_context(db, "replenish", store_id)
    )


@pages_router.get("/stock/consume")
def stock_consume_page(
    request: Request,
    db: Session = Depends(get_db),
    store_id: Optional[int] = Query(None, gt=0),
):
    return templates.TemplateResponse(
        request, "stock.html", _stock_page_context(db, "consume", store_id)
    )

ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


def _validate_store_exists(db: Session, store_id: int) -> None:
    crud.require_store_id_for_stock(store_id)
    if not crud.get_store(db, store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")


@router.get("/quantity", response_model=StockQuantityOut)
def get_stock_quantity(
    store_id: int = Query(..., gt=0),
    product_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """店舗×商品の現在庫（モーダル用・リアルタイム取得）"""
    check_store_access(current_user, store_id)
    _validate_store_exists(db, store_id)
    try:
        qty, unit, on_shelf = crud_stock.get_product_quantity_at_store(
            db, store_id, product_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return StockQuantityOut(
        store_id=store_id,
        product_id=product_id,
        quantity=qty,
        unit=unit,
        is_on_shelf=on_shelf,
    )


@router.get("/lookup", response_model=StockLookupOut)
def lookup_product(
    store_id: int = Query(...),
    code: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """スキャンコードで商品・現在庫を照合"""
    check_store_access(current_user, store_id)
    _validate_store_exists(db, store_id)
    return crud_stock.lookup_stock_product(db, store_id, code)


@router.post("/register", response_model=InventoryScanResponse)
def register_stock(
    body: StockRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """商品ID指定で在庫を増減"""
    check_store_access(current_user, body.store_id)
    _validate_store_exists(db, body.store_id)
    try:
        return crud_stock.register_stock(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/register-with-product", response_model=InventoryScanResponse)
def register_with_new_product(
    body: StockRegisterWithProductRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """未登録商品を新規登録してから在庫反映"""
    check_store_access(current_user, body.store_id)
    _validate_store_exists(db, body.store_id)
    try:
        return crud_stock.register_stock_with_new_product(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/bulk-register")
def bulk_register(
    body: StockBulkRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """複数商品をまとめて在庫反映"""
    check_store_access(current_user, body.store_id)
    _validate_store_exists(db, body.store_id)
    try:
        return crud_stock.bulk_register_stock(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/bulk-parse", response_model=StockBulkParseResult)
async def bulk_parse(
    file: UploadFile = File(...),
    store_id: int = Query(...),
    dealer_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """写真・PDFから明細を読み取りマスタと照合"""
    check_store_access(current_user, store_id)
    _validate_store_exists(db, store_id)

    media = file.content_type or "image/jpeg"
    if media not in ALLOWED_TYPES:
        raise HTTPException(400, "JPEG / PNG / WebP / PDF のみ対応しています。")

    raw = await file.read()
    try:
        parsed = parse_invoice_file(raw, media)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return crud_stock.build_stock_bulk_parse_result(db, store_id, parsed, dealer_id)
