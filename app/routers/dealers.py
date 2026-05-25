"""ディーラーマスタ API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud_masters
from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import DealerMaker, User
from app.schemas import (
    DealerCreate,
    DealerMakerCreate,
    DealerMakerOut,
    DealerOut,
    DealerUpdate,
)

router = APIRouter()


@router.get("", response_model=list[DealerOut])
def list_dealers(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return crud_masters.get_dealers(db, active_only=True)


@router.get("/all", response_model=list[DealerOut])
def list_dealers_all(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return crud_masters.get_dealers(db, active_only=False)


@router.post("", response_model=DealerOut)
def create_dealer(body: DealerCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return crud_masters.create_dealer(db, body)


@router.put("/{dealer_id}", response_model=DealerOut)
def update_dealer(
    dealer_id: int,
    body: DealerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    d = crud_masters.get_dealer(db, dealer_id)
    if not d:
        raise HTTPException(404, "ディーラーが見つかりません。")
    return crud_masters.update_dealer(db, d, body)


@router.delete("/{dealer_id}", status_code=204)
def deactivate_dealer(dealer_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    d = crud_masters.get_dealer(db, dealer_id)
    if not d:
        raise HTTPException(404, "ディーラーが見つかりません。")
    crud_masters.deactivate_dealer(db, d)


@router.get("/{dealer_id}/makers", response_model=list[DealerMakerOut])
def dealer_makers(dealer_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return crud_masters.list_dealer_makers(db, dealer_id=dealer_id)


@router.post("/links", response_model=DealerMakerOut)
def link_dealer_maker(
    body: DealerMakerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    dm = crud_masters.create_dealer_maker(db, body)
    return crud_masters.list_dealer_makers(db, dealer_id=dm.dealer_id)[-1]


@router.delete("/links/{link_id}", status_code=204)
def unlink_dealer_maker(link_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    dm = db.query(DealerMaker).filter(DealerMaker.id == link_id).first()
    if not dm:
        raise HTTPException(404, "紐付けが見つかりません。")
    crud_masters.deactivate_dealer_maker(db, dm)
