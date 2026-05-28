"""
在庫増減ログに基づく分析（発注データ分析画面の「棚の動き」）
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.crud_order_analytics import OrderFilter
from app.models import Category, Inventory, InventoryAction, InventoryLog, Product, Store


def _product_matches_filter(product: Product, f: OrderFilter) -> bool:
    if f.section and (not product.category or product.category.section != f.section):
        return False
    if f.category_id and product.category_id != f.category_id:
        return False
    if f.dealer_id and product.dealer_id != f.dealer_id:
        return False
    if f.maker_id and product.maker_id != f.maker_id:
        return False
    if f.brand_id and product.brand_id != f.brand_id:
        return False
    return True
from app.schemas import (
    InventoryAnalyticsOut,
    StagnantProductRowOut,
    StoreAssortmentRowOut,
    StorePopularityRowOut,
)


def _log_date_filter(q, f: OrderFilter):
    """InventoryLog.created_at に期間フィルタ"""
    if f.date_from:
        q = q.filter(InventoryLog.created_at >= datetime.combine(f.date_from, datetime.min.time()))
    if f.date_to:
        q = q.filter(
            InventoryLog.created_at
            <= datetime.combine(f.date_to, datetime.max.time())
        )
    if f.year and not f.date_from:
        q = q.filter(func.extract("year", InventoryLog.created_at) == f.year)
    if f.month and not f.date_from:
        q = q.filter(func.extract("month", InventoryLog.created_at) == f.month)
    if f.store_id:
        q = q.filter(InventoryLog.store_id == f.store_id)
    return q


def get_store_popularity(
    db: Session, f: OrderFilter, *, limit: int = 50
) -> list[StorePopularityRowOut]:
    """店舗別人気商品（使用ログの回数・数量）"""
    q = (
        db.query(
            Store.id,
            Store.name,
            Product.id,
            Product.name,
            func.count(InventoryLog.id).label("use_count"),
            func.sum(InventoryLog.quantity_change).label("use_qty"),
        )
        .join(Store, Store.id == InventoryLog.store_id)
        .join(Product, Product.id == InventoryLog.product_id)
        .options(joinedload(Product.category))
        .filter(InventoryLog.action == InventoryAction.USE)
    )
    q = _log_date_filter(q, f)
    if f.section:
        q = q.join(Category, Category.id == Product.category_id).filter(
            Category.section == f.section
        )
    if f.category_id:
        q = q.filter(Product.category_id == f.category_id)
    if f.dealer_id:
        q = q.filter(Product.dealer_id == f.dealer_id)
    if f.maker_id:
        q = q.filter(Product.maker_id == f.maker_id)
    if f.brand_id:
        q = q.filter(Product.brand_id == f.brand_id)
    rows = (
        q.group_by(Store.id, Product.id)
        .order_by(func.sum(InventoryLog.quantity_change).desc())
        .limit(limit)
        .all()
    )
    result: list[StorePopularityRowOut] = []
    for rank, r in enumerate(rows, start=1):
        result.append(
            StorePopularityRowOut(
                store_id=r[0],
                store_name=r[1],
                product_id=r[2],
                product_name=r[3],
                use_count=int(r[4] or 0),
                use_quantity=int(r[5] or 0),
                rank=rank,
            )
        )
    return result


def get_stagnant_products(
    db: Session,
    store_id: Optional[int] = None,
    *,
    days: int = 30,
) -> list[StagnantProductRowOut]:
    """is_active=true だが N 日以上増減ログがない商品"""
    since = datetime.utcnow() - timedelta(days=days)
    q = (
        db.query(Inventory)
        .options(
            joinedload(Inventory.product).joinedload(Product.category),
            joinedload(Inventory.store),
        )
        .filter(Inventory.is_active.is_(True))
    )
    if store_id:
        q = q.filter(Inventory.store_id == store_id)

    result: list[StagnantProductRowOut] = []
    for inv in q.all():
        if not _product_matches_filter(inv.product, f):
            continue
        last_log = (
            db.query(func.max(InventoryLog.created_at))
            .filter(
                InventoryLog.store_id == inv.store_id,
                InventoryLog.product_id == inv.product_id,
            )
            .scalar()
        )
        if last_log and last_log >= since:
            continue
        if last_log:
            delta_days = (datetime.utcnow() - last_log).days
        else:
            delta_days = days + 1
        result.append(
            StagnantProductRowOut(
                store_id=inv.store_id,
                store_name=inv.store.name,
                product_id=inv.product_id,
                product_name=inv.product.name,
                quantity=inv.quantity,
                unit=inv.product.unit or "本",
                days_without_movement=delta_days,
            )
        )
    result.sort(key=lambda x: (-x.days_without_movement, x.store_name, x.product_name))
    return result


def get_store_assortment_comparison(db: Session) -> list[StoreAssortmentRowOut]:
    """店舗別品揃え（is_active の SKU 数・カテゴリ内訳）"""
    stores = db.query(Store).filter(Store.is_active.is_(True)).order_by(Store.name).all()
    result: list[StoreAssortmentRowOut] = []

    for store in stores:
        rows = (
            db.query(Inventory)
            .join(Product, Product.id == Inventory.product_id)
            .join(Category, Category.id == Product.category_id)
            .filter(
                Inventory.store_id == store.id,
                Inventory.is_active.is_(True),
            )
            .all()
        )
        breakdown: dict[str, int] = {}
        for inv in rows:
            cat_name = inv.product.category.name if inv.product.category else "未分類"
            breakdown[cat_name] = breakdown.get(cat_name, 0) + 1
        result.append(
            StoreAssortmentRowOut(
                store_id=store.id,
                store_name=store.name,
                active_sku_count=len(rows),
                category_breakdown=breakdown,
            )
        )
    return result


def get_inventory_analytics(
    db: Session, f: OrderFilter, stagnant_days: int = 30
) -> InventoryAnalyticsOut:
    return InventoryAnalyticsOut(
        popularity=get_store_popularity(db, f),
        stagnant=get_stagnant_products(db, f.store_id, days=stagnant_days),
        assortment=get_store_assortment_comparison(db),
    )
