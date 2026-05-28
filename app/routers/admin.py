"""管理者用（/admin 配下）API

管理画面のモーダルから使いやすい形のエンドポイントを提供する。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import crud
from app.auth import check_store_access, get_current_user, require_admin
from app.database import get_db
from app.models import User
from app.schemas import (
    BrandOut,
    InventoryLogEditOut,
    MakerOut,
    StoreProductSettingProductOut,
    StoreProductSettingProductPut,
)


router = APIRouter()


class DealerMakerLinkBody(BaseModel):
    maker_id: int = Field(gt=0)


@router.get("/dealers/{dealer_id}/makers", response_model=list[MakerOut])
def admin_get_dealer_makers(
    dealer_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return crud.get_makers_linked_to_dealer(db, dealer_id)


@router.post("/dealers/{dealer_id}/makers", response_model=MakerOut)
def admin_add_dealer_maker(
    dealer_id: int,
    body: DealerMakerLinkBody,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        return crud.link_maker_to_dealer(db, dealer_id=dealer_id, maker_id=body.maker_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/dealers/{dealer_id}/makers/{maker_id}", status_code=204)
def admin_remove_dealer_maker(
    dealer_id: int,
    maker_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    if not crud.unlink_maker_from_dealer(db, dealer_id=dealer_id, maker_id=maker_id):
        raise HTTPException(status_code=404, detail="紐付けが見つかりません。")


@router.get("/makers/{maker_id}/brands", response_model=list[BrandOut])
def admin_get_maker_brands(
    maker_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        return crud.get_brands_linked_to_maker(db, maker_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/makers/{maker_id}/brands/{brand_id}", response_model=BrandOut)
def admin_add_maker_brand(
    maker_id: int,
    brand_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        return crud.link_brand_to_maker(db, maker_id=maker_id, brand_id=brand_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/makers/{maker_id}/brands/{brand_id}", status_code=204)
def admin_remove_maker_brand(
    maker_id: int,
    brand_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    if not crud.unlink_brand_from_maker(db, maker_id=maker_id, brand_id=brand_id):
        raise HTTPException(status_code=404, detail="紐付けが見つかりません。")


@router.get("/inventory-log-edits", response_model=list[InventoryLogEditOut])
def admin_list_inventory_log_edits(
    limit: int = 200,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """在庫登録の修正ログ（管理者のみ）"""
    return crud.list_inventory_log_edits(db, limit=limit)


@router.get("/store-settings/product", response_model=StoreProductSettingProductOut)
def get_store_product_setting(
    store_id: int = Query(..., gt=0),
    product_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """店舗×商品の発注目安を取得（store_product_settings 優先）"""
    check_store_access(current_user, store_id)
    if not crud.get_store(db, store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")
    try:
        return crud.get_store_product_setting(db, store_id, product_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/store-settings/product", response_model=StoreProductSettingProductOut)
def put_store_product_setting(
    body: StoreProductSettingProductPut,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """店舗×商品の発注目安を UPSERT（全画面共通）"""
    check_store_access(current_user, body.store_id)
    if not crud.get_store(db, body.store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")

    product = crud.get_product_by_id(db, body.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品が見つかりません。")

    warning = (
        body.warning_threshold
        if body.warning_threshold is not None
        else product.warning_threshold
    )
    critical = (
        body.critical_threshold
        if body.critical_threshold is not None
        else product.critical_threshold
    )

    try:
        crud.upsert_store_product_setting_product(
            db,
            body.store_id,
            body.product_id,
            standard_stock=body.standard_stock,
            warning_threshold=warning,
            critical_threshold=critical,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return crud.get_store_product_setting(db, body.store_id, body.product_id)
