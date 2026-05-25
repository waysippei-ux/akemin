"""
棚補充・使用 API
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app import crud, crud_stock
from app.auth import check_store_access, get_current_user
from app.database import get_db
from app.models import User
from app.schemas import (
    InventoryScanResponse,
    StockBulkParseResult,
    StockBulkRegisterRequest,
    StockLookupOut,
    StockRegisterRequest,
    StockRegisterWithProductRequest,
)
from app.services.invoice_parser import parse_invoice_file

router = APIRouter()

ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


@router.get("/lookup", response_model=StockLookupOut)
def lookup_product(
    store_id: int = Query(...),
    code: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """スキャンコードで商品・現在庫を照合"""
    check_store_access(current_user, store_id)
    if not crud.get_store(db, store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")
    return crud_stock.lookup_stock_product(db, store_id, code)


@router.post("/register", response_model=InventoryScanResponse)
def register_stock(
    body: StockRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """商品ID指定で在庫を増減"""
    check_store_access(current_user, body.store_id)
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
    if not crud.get_store(db, store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")

    media = file.content_type or "image/jpeg"
    if media not in ALLOWED_TYPES:
        raise HTTPException(400, "JPEG / PNG / WebP / PDF のみ対応しています。")

    raw = await file.read()
    try:
        parsed = parse_invoice_file(raw, media)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return crud_stock.build_stock_bulk_parse_result(db, store_id, parsed, dealer_id)
