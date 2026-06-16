"""ダッシュボード API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import crud, crud_masters
from app.auth import check_store_access, get_current_user
from app.database import get_db
from app.models import User
from app.schemas import (
    CategorySummaryOut,
    DashboardSectionsOut,
    OrderingCandidateOut,
    OrderingDeliverBody,
    OrderingItemOut,
    OrderingItemsSaveBody,
)

router = APIRouter()
ordering_router = APIRouter(tags=["発注中"])


@router.get("/sections", response_model=DashboardSectionsOut)
def dashboard_sections(
    store_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """TOP 2セクション（材料の棚 / 販売商品の棚）

    カテゴリ集計は crud_masters._summarize_category で
    Inventory.is_active == True の商品のみカウントする。
    """
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


@ordering_router.get("/ordering-items", response_model=list[OrderingItemOut])
def get_ordering_items(
    store_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """発注中一覧（ordering_items テーブル）— GET /api/ordering-items?store_id="""
    check_store_access(current_user, store_id)
    rows = crud.list_ordering_items(db, store_id)
    return [
        OrderingItemOut(
            id=row.id,
            product_id=row.product_id,
            product_name=row.product.name,
            brand_name=row.product.brand.name if row.product.brand else None,
            ordered_quantity=row.ordered_quantity,
        )
        for row in rows
    ]


@ordering_router.get(
    "/ordering-items/candidates",
    response_model=list[OrderingCandidateOut],
)
def get_ordering_candidates(
    store_id: int = Query(..., gt=0),
    shelf_id: int = Query(..., gt=0, description="棚（sections.id）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """発注中登録モーダル用：黄アラート以下の商品一覧"""
    check_store_access(current_user, store_id)
    try:
        items = crud.get_ordering_candidates_for_shelf(db, store_id, shelf_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return [OrderingCandidateOut(**item) for item in items]


@ordering_router.post("/ordering-items")
def save_ordering_items(
    body: OrderingItemsSaveBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """発注中登録・更新"""
    check_store_access(current_user, body.store_id)
    try:
        crud.save_ordering_items(
            db,
            body.store_id,
            [item.model_dump() for item in body.items],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"message": "発注中を登録しました"}


@ordering_router.delete("/ordering-items/{item_id}")
def delete_ordering_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """発注中削除"""
    from app.models import OrderingItem

    row = db.query(OrderingItem).filter(OrderingItem.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="発注中データが見つかりません。")
    check_store_access(current_user, row.store_id)
    crud.delete_ordering_item(db, item_id)
    return {"message": "削除しました"}


@ordering_router.post("/ordering-items/deliver")
def deliver_ordering_items(
    body: OrderingDeliverBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """納品登録（在庫に加算・発注中レコード削除）

    crud.deliver_ordering_items 内で各 item_id について:
    - 在庫 quantity に ordered_quantity を加算
    - inventory_logs に RESTOCK を記録
    - ordering_items から db.delete(ordering) で削除
    """
    check_store_access(current_user, body.store_id)
    if not body.item_ids:
        raise HTTPException(status_code=400, detail="納品登録する商品を選択してください。")
    try:
        count = crud.deliver_ordering_items(
            db, current_user, body.store_id, body.item_ids
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if count == 0:
        raise HTTPException(status_code=404, detail="納品対象が見つかりません。")
    return {"message": "納品登録しました", "delivered_count": count}
