"""メーカーマスタ API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud_masters
from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User
from app.schemas import MakerCreate, MakerOut, MakerUpdate

router = APIRouter()


@router.get("", response_model=list[MakerOut])
def list_makers(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return crud_masters.get_makers(db, active_only=True)


@router.get("/all", response_model=list[MakerOut])
def list_makers_all(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return crud_masters.get_makers(db, active_only=False)


@router.post("", response_model=MakerOut)
def create_maker(body: MakerCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return crud_masters.create_maker(db, body)


@router.put("/{maker_id}", response_model=MakerOut)
def update_maker(
    maker_id: int,
    body: MakerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    m = crud_masters.get_maker(db, maker_id)
    if not m:
        raise HTTPException(404, "メーカーが見つかりません。")
    return crud_masters.update_maker(db, m, body)


@router.delete("/{maker_id}", status_code=204)
def delete_maker(
    maker_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    m = crud_masters.get_maker(db, maker_id)
    if not m:
        raise HTTPException(404, "メーカーが見つかりません。")
    try:
        crud_masters.delete_maker(db, m)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
