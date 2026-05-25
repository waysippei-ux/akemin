"""ダッシュボード API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import crud_masters
from app.auth import check_store_access, get_current_user
from app.database import get_db
from app.models import User
from app.schemas import CategorySummaryOut, DashboardSectionsOut

router = APIRouter()


@router.get("/sections", response_model=DashboardSectionsOut)
def dashboard_sections(
    store_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """TOP 2セクション（材料の棚 / 販売商品の棚）"""
    check_store_access(current_user, store_id)
    return crud_masters.get_dashboard_sections(db, store_id)


@router.get("/categories", response_model=list[CategorySummaryOut])
def category_summaries(
    store_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """後方互換: 全カテゴリ一覧"""
    check_store_access(current_user, store_id)
    return crud_masters.get_category_summaries(db, store_id)
