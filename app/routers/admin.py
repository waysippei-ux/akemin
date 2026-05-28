"""管理者用（/admin 配下）API

管理画面のモーダルから使いやすい形のエンドポイントを提供する。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import crud
from app.auth import require_admin
from app.database import get_db
from app.schemas import BrandOut, InventoryLogEditOut, MakerOut


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
