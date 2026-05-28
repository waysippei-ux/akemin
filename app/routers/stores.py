"""
店舗 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User, UserRole
from app import crud_store_settings
from app.schemas import (
    StoreCreate,
    StoreOut,
    StoreProductSettingRowOut,
    StoreProductSettingUpsert,
    StoreUpdate,
)

router = APIRouter()


@router.get("", response_model=list[StoreOut])
def list_stores(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    店舗一覧（有効な店舗のみ）
    - 管理者: 全店舗
    - スタッフ: 所属店舗のみ
    """
    stores = crud.get_stores(db, active_only=True)
    if current_user.role == UserRole.STAFF and current_user.store_id:
        stores = [s for s in stores if s.id == current_user.store_id]
    return stores


@router.get("/all", response_model=list[StoreOut])
def list_stores_all(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """管理者用 — 無効店舗を含む一覧"""
    return crud.get_stores(db, active_only=False)


@router.post("", response_model=StoreOut)
def create_store(
    body: StoreCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "店舗名を入力してください。")
    return crud.create_store(db, name)


@router.get("/{store_id}/product-settings", response_model=list[StoreProductSettingRowOut])
def list_store_product_settings(
    store_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """店舗別発注目安一覧（管理者のみ）"""
    if not crud.get_store(db, store_id):
        raise HTTPException(404, "店舗が見つかりません。")
    return crud_store_settings.list_store_product_settings(db, store_id)


@router.put("/{store_id}/product-settings/{product_id}", response_model=StoreProductSettingRowOut)
def upsert_store_product_setting(
    store_id: int,
    product_id: int,
    body: StoreProductSettingUpsert,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """店舗別の黄・赤閾値を設定（管理者のみ）"""
    if not crud.get_store(db, store_id):
        raise HTTPException(404, "店舗が見つかりません。")
    try:
        if body.standard_stock is not None:
            product = crud.get_product_by_id(db, product_id)
            if not product:
                raise HTTPException(404, "商品が見つかりません。")
            product.standard_stock = body.standard_stock
            db.commit()
        crud_store_settings.upsert_store_product_setting(
            db,
            store_id,
            product_id,
            body.warning_threshold,
            body.critical_threshold,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    rows = crud_store_settings.list_store_product_settings(db, store_id)
    row = next((r for r in rows if r["product_id"] == product_id), None)
    if not row:
        raise HTTPException(404, "商品が見つかりません。")
    return row


@router.delete("/{store_id}/product-settings/{product_id}", status_code=204)
def clear_store_product_setting(
    store_id: int,
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """店舗別設定を削除しデフォルトに戻す（管理者のみ）"""
    if not crud.get_store(db, store_id):
        raise HTTPException(404, "店舗が見つかりません。")
    crud_store_settings.delete_store_product_setting(db, store_id, product_id)


@router.put("/{store_id}", response_model=StoreOut)
def update_store(
    store_id: int,
    body: StoreUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    store = crud.get_store(db, store_id)
    if not store:
        raise HTTPException(404, "店舗が見つかりません。")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "店舗名を入力してください。")
    return crud.update_store(db, store, name=name, is_active=body.is_active)


@router.delete("/{store_id}", status_code=204)
def delete_store(
    store_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    store = crud.get_store(db, store_id)
    if not store:
        raise HTTPException(404, "店舗が見つかりません。")
    try:
        crud.delete_store(db, store)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
