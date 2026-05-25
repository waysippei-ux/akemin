"""
在庫 API（一覧・バーコードスキャン）
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud
from app.auth import check_store_access, get_current_user
from app.database import get_db
from app.models import User
from app.schemas import (
    InventoryItemOut,
    InventoryScanRequest,
    InventoryScanResponse,
)

router = APIRouter()


@router.get("/store/{store_id}", response_model=list[InventoryItemOut])
def get_store_inventory(
    store_id: int,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """店舗の在庫一覧（色分け付き）。active_only=false で補充画面用に全商品"""
    check_store_access(current_user, store_id)
    if not crud.get_store(db, store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")
    return crud.get_inventory_list(db, store_id, active_only=active_only)


@router.get("/store/{store_id}/category/{category_id}", response_model=list[InventoryItemOut])
def get_store_inventory_by_category(
    store_id: int,
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """店舗×カテゴリの在庫一覧"""
    check_store_access(current_user, store_id)
    if not crud.get_store(db, store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")
    return crud.get_inventory_list(
        db, store_id, category_id=category_id, active_only=True
    )


@router.post("/scan", response_model=InventoryScanResponse)
def scan_barcode(
    body: InventoryScanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """バーコードスキャンで在庫を増減（使用 / 補充）"""
    check_store_access(current_user, body.store_id)
    try:
        return crud.scan_inventory(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
