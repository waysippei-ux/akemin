"""ブランドマスタ API"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import crud_masters
from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User
from app.schemas import BrandCreate, BrandOut, BrandUpdate

router = APIRouter()


@router.get("", response_model=list[BrandOut])
def list_brands(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    maker_id: Optional[int] = Query(None, gt=0),
):
    brands = crud_masters.get_brands(db, maker_id=maker_id, active_maker_only=True)
    return [crud_masters.brand_to_out(b) for b in brands]


@router.get("/all", response_model=list[BrandOut])
def list_brands_all(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    maker_id: Optional[int] = Query(None, gt=0),
):
    brands = crud_masters.get_brands(db, maker_id=maker_id, active_maker_only=False)
    return [crud_masters.brand_to_out(b) for b in brands]


@router.post("", response_model=BrandOut)
def create_brand(
    body: BrandCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    try:
        brand = crud_masters.create_brand(db, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return crud_masters.brand_to_out(brand)


@router.put("/{brand_id}", response_model=BrandOut)
def update_brand(
    brand_id: int,
    body: BrandUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    brand = crud_masters.get_brand(db, brand_id)
    if not brand:
        raise HTTPException(404, "ブランドが見つかりません。")
    try:
        brand = crud_masters.update_brand(db, brand, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return crud_masters.brand_to_out(brand)


@router.delete("/{brand_id}", status_code=204)
def delete_brand(
    brand_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    brand = crud_masters.get_brand(db, brand_id)
    if not brand:
        raise HTTPException(404, "ブランドが見つかりません。")
    crud_masters.delete_brand(db, brand)
