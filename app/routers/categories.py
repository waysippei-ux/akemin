"""カテゴリマスタ API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud_masters
from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User
from app.schemas import CategoryCreate, CategoryOrderUpdate, CategoryOut, CategoryUpdate

router = APIRouter()


@router.get("", response_model=list[CategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    include_inactive: bool = False,
):
    cats = crud_masters.get_categories(db, active_only=not include_inactive)
    return [crud_masters.category_to_out(db, c) for c in cats]


@router.post("", response_model=CategoryOut)
def create_category(
    body: CategoryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    try:
        cat = crud_masters.create_category(db, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return crud_masters.category_to_out(db, cat)


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    cat = crud_masters.get_category(db, category_id)
    if not cat:
        raise HTTPException(404, "カテゴリが見つかりません。")
    if not crud_masters.get_section(db, body.section):
        raise HTTPException(400, "指定された棚が見つかりません。")
    cat = crud_masters.update_category(db, cat, body)
    return crud_masters.category_to_out(db, cat)


@router.put("/{category_id}/order", response_model=CategoryOut)
def reorder_category(
    category_id: int,
    body: CategoryOrderUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    cat = crud_masters.get_category(db, category_id)
    if not cat:
        raise HTTPException(404, "カテゴリが見つかりません。")
    cat = crud_masters.reorder_category(db, cat, body.direction)
    return crud_masters.category_to_out(db, cat)


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    cat = crud_masters.get_category(db, category_id)
    if not cat:
        raise HTTPException(404, "カテゴリが見つかりません。")
    try:
        crud_masters.delete_category(db, cat)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
