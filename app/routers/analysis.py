"""
AI 在庫分析 API
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import crud
from app.auth import check_store_access, get_current_user
from app.database import get_db
from app.models import User
from app.schemas import AnalysisResponse
from app.services.inventory_analysis import analyze_inventory

router = APIRouter()


@router.get("/store/{store_id}", response_model=AnalysisResponse)
def get_inventory_analysis(
    store_id: int,
    category_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Claude による在庫分析アドバイス（日本語）"""
    check_store_access(current_user, store_id)
    store = crud.get_store(db, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")

    advice = analyze_inventory(db, store_id, category_id=category_id)
    return AnalysisResponse(
        store_id=store_id,
        store_name=store.name,
        category_id=category_id,
        advice=advice,
    )
