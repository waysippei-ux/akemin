"""棚（sections）マスタ API"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud_masters
from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User
from app.schemas import SectionCreate, SectionOut, SectionUpdate

router = APIRouter()


@router.get("", response_model=list[SectionOut])
def list_sections(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    include_inactive: bool = False,
):
    sections = crud_masters.get_sections(db, active_only=not include_inactive)
    return [crud_masters.section_to_out(db, s) for s in sections]


@router.post("", response_model=SectionOut, status_code=status.HTTP_201_CREATED)
def create_section(
    body: SectionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sec = crud_masters.create_section(db, body)
    return crud_masters.section_to_out(db, sec)


@router.put("/{section_id}", response_model=SectionOut)
def update_section(
    section_id: int,
    body: SectionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sec = crud_masters.get_section(db, section_id)
    if not sec:
        raise HTTPException(404, "棚が見つかりません。")
    sec = crud_masters.update_section(db, sec, body)
    return crud_masters.section_to_out(db, sec)


@router.delete("/{section_id}", status_code=204)
def delete_section(
    section_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sec = crud_masters.get_section(db, section_id)
    if not sec:
        raise HTTPException(404, "棚が見つかりません。")
    try:
        crud_masters.delete_section(db, sec)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
