"""カテゴリマスタ API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud_masters
from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter()


@router.get("", response_model=list[CategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    include_inactive: bool = False,
):
    return crud_masters.get_categories(db, active_only=not include_inactive)


@router.post("", response_model=CategoryOut)
def create_category(
    body: CategoryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return crud_masters.create_category(db, body)


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
    return crud_masters.update_category(db, cat, body)


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
