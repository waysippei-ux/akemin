"""
棚補充・使用 — 画面ルート・API
"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, crud_masters, crud_stock
from app.auth import check_store_access, get_current_user
from app.config import BASE_DIR
from app.database import get_db
from app.models import InventoryAction, User
from app.schemas import (
    CategoryOut,
    DealerOut,
    InventoryItemOut,
    InventoryScanResponse,
    MakerOut,
    StockBulkParseResult,
    StockBulkRegisterRequest,
    StockConsumeRequest,
    StockLookupOut,
    StockQuantityOut,
    StockRegisterWithProductRequest,
    StockReplenishRequest,
    StoreOut,
)
from app.services.invoice_parser import parse_invoice_file

templates = Jinja2Templates(directory=str((BASE_DIR / "templates").resolve()))

pages_router = APIRouter(tags=["棚補充・使用 画面"])
router = APIRouter()

ALLOWED_UPLOAD_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


def _masters(db: Session) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
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
    return stores, categories, makers, dealers


def _resolve_default_store_id(
    stores: list[dict], store_id: Optional[int]
) -> Optional[int]:
    store_ids = {s["id"] for s in stores}
    if store_id and store_id in store_ids:
        return store_id
    return stores[0]["id"] if stores else None


def _products_for_store(
    db: Session, store_id: int, *, active_only: bool
) -> list[dict[str, Any]]:
    return [
        InventoryItemOut.model_validate(item).model_dump(mode="json")
        for item in crud.get_inventory_list(db, store_id, active_only=active_only)
    ]


def _page_context(
    db: Session,
    page: Literal["replenish", "consume"],
    store_id: Optional[int] = None,
) -> dict[str, Any]:
    stores, categories, makers, dealers = _masters(db)
    default_store_id = _resolve_default_store_id(stores, store_id)
    active_only = page == "consume"
    products: list[dict[str, Any]] = []
    if default_store_id is not None:
        products = _products_for_store(db, default_store_id, active_only=active_only)

    page_json = {
        "page": page,
        "stores": stores,
        "categories": categories,
        "makers": makers,
        "dealers": dealers,
        "products": products,
        "default_store_id": default_store_id,
    }
    return {
        "stores": stores,
        "categories": categories,
        "makers": makers,
        "dealers": dealers,
        "products": products,
        "default_store_id": default_store_id,
        "page_json": json.dumps(page_json, ensure_ascii=False),
    }


@pages_router.get("/stock/replenish")
def stock_replenish_page(
    request: Request,
    db: Session = Depends(get_db),
    store_id: Optional[int] = Query(None, gt=0),
):
    return templates.TemplateResponse(
        request, "stock_replenish.html", _page_context(db, "replenish", store_id)
    )


@pages_router.get("/stock/consume")
def stock_consume_page(
    request: Request,
    db: Session = Depends(get_db),
    store_id: Optional[int] = Query(None, gt=0),
):
    return templates.TemplateResponse(
        request, "stock_consume.html", _page_context(db, "consume", store_id)
    )


def _validate_store(db: Session, store_id: int) -> None:
    crud.require_store_id_for_stock(store_id)
    if not crud.get_store(db, store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")


@router.get("/products", response_model=list[InventoryItemOut])
def list_stock_products(
    store_id: int = Query(..., gt=0),
    page: Literal["replenish", "consume"] = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """店舗切り替え時の商品一覧"""
    check_store_access(current_user, store_id)
    _validate_store(db, store_id)
    active_only = page == "consume"
    return crud.get_inventory_list(db, store_id, active_only=active_only)


@router.get("/quantity", response_model=StockQuantityOut)
def get_stock_quantity(
    store_id: int = Query(..., gt=0),
    product_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """店舗×商品の現在庫（モーダル用）"""
    check_store_access(current_user, store_id)
    _validate_store(db, store_id)
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


@router.post("/replenish", response_model=InventoryScanResponse)
def replenish_stock(
    body: StockReplenishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """棚補充（在庫+・is_active=true）"""
    check_store_access(current_user, body.store_id)
    _validate_store(db, body.store_id)
    try:
        return crud_stock.replenish_stock(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/consume", response_model=InventoryScanResponse)
def consume_stock(
    body: StockConsumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """使用済み（在庫-・0未満不可）"""
    check_store_access(current_user, body.store_id)
    _validate_store(db, body.store_id)
    try:
        return crud_stock.consume_stock(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/lookup", response_model=StockLookupOut)
def lookup_product(
    store_id: int = Query(..., gt=0),
    code: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """バーコードで商品照合"""
    check_store_access(current_user, store_id)
    _validate_store(db, store_id)
    return crud_stock.lookup_stock_product(db, store_id, code)


@router.post("/register-with-product", response_model=InventoryScanResponse)
def register_with_new_product(
    body: StockRegisterWithProductRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """未登録商品を新規登録してから棚に反映（補充用）"""
    check_store_access(current_user, body.store_id)
    _validate_store(db, body.store_id)
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
    _validate_store(db, body.store_id)
    try:
        return crud_stock.bulk_register_stock(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/bulk-parse", response_model=StockBulkParseResult)
async def bulk_parse(
    file: UploadFile = File(...),
    store_id: int = Query(..., gt=0),
    dealer_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """写真・PDFから明細を読み取りマスタと照合"""
    check_store_access(current_user, store_id)
    _validate_store(db, store_id)

    media = file.content_type or "image/jpeg"
    if media not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(400, "JPEG / PNG / WebP / PDF のみ対応しています。")

    raw = await file.read()
    try:
        parsed = parse_invoice_file(raw, media)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return crud_stock.build_stock_bulk_parse_result(db, store_id, parsed, dealer_id)
