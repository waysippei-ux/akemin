"""
店舗 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User, UserRole
from app.schemas import StoreCreate, StoreOut, StoreUpdate

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
