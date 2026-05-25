"""
マスタ（カテゴリ・ディーラー・メーカー）と発注の CRUD
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import extract, func
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Category,
    CategorySection,
    Dealer,
    DealerMaker,
    Inventory,
    InventoryAction,
    InventoryLog,
    Maker,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Store,
    User,
)
from app.schemas import (
    CategoryCreate,
    CategoryOut,
    CategorySummaryOut,
    CategoryUpdate,
    DashboardSectionsOut,
    DealerCreate,
    DealerMakerCreate,
    DealerMakerOut,
    DealerOut,
    DealerUpdate,
    InventoryItemOut,
    MakerCreate,
    MakerOut,
    MakerUpdate,
    ProductOut,
    PurchaseOrderItemOut,
    PurchaseOrderListItem,
    PurchaseOrderOut,
    StockLevel,
)
from app.crud import calc_stock_level, get_or_create_inventory, get_store
from app.crud_store_settings import get_settings_map, resolve_thresholds


# ---------------------------------------------------------------------------
# カテゴリ
# ---------------------------------------------------------------------------

def get_categories(
    db: Session, active_only: bool = True, section: Optional[int] = None
) -> list[Category]:
    q = db.query(Category)
    if active_only:
        q = q.filter(Category.is_active.is_(True))
    if section is not None:
        q = q.filter(Category.section == section)
    return q.order_by(Category.section, Category.sort_order, Category.id).all()


def get_category(db: Session, category_id: int) -> Category | None:
    return db.query(Category).filter(Category.id == category_id).first()


def create_category(db: Session, data: CategoryCreate) -> Category:
    cat = Category(
        name=data.name,
        section=data.section,
        sort_order=data.sort_order,
        is_active=True,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def update_category(db: Session, cat: Category, data: CategoryUpdate) -> Category:
    cat.name = data.name
    cat.section = data.section
    cat.sort_order = data.sort_order
    cat.is_active = data.is_active
    db.commit()
    db.refresh(cat)
    return cat


def deactivate_category(db: Session, cat: Category) -> None:
    cat.is_active = False
    db.commit()


# ---------------------------------------------------------------------------
# ディーラー
# ---------------------------------------------------------------------------

def get_dealers(db: Session, active_only: bool = True) -> list[Dealer]:
    q = db.query(Dealer)
    if active_only:
        q = q.filter(Dealer.is_active.is_(True))
    return q.order_by(Dealer.name).all()


def get_dealer(db: Session, dealer_id: int) -> Dealer | None:
    return db.query(Dealer).filter(Dealer.id == dealer_id).first()


def get_dealer_by_name(db: Session, name: str) -> Dealer | None:
    return db.query(Dealer).filter(Dealer.name == name, Dealer.is_active.is_(True)).first()


def create_dealer(db: Session, data: DealerCreate) -> Dealer:
    d = Dealer(name=data.name, contact_info=data.contact_info, is_active=True)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def update_dealer(db: Session, dealer: Dealer, data: DealerUpdate) -> Dealer:
    dealer.name = data.name
    dealer.contact_info = data.contact_info
    dealer.is_active = data.is_active
    db.commit()
    db.refresh(dealer)
    return dealer


def deactivate_dealer(db: Session, dealer: Dealer) -> None:
    dealer.is_active = False
    db.commit()


# ---------------------------------------------------------------------------
# メーカー
# ---------------------------------------------------------------------------

def get_makers(db: Session, active_only: bool = True) -> list[Maker]:
    q = db.query(Maker)
    if active_only:
        q = q.filter(Maker.is_active.is_(True))
    return q.order_by(Maker.name).all()


def get_maker(db: Session, maker_id: int) -> Maker | None:
    return db.query(Maker).filter(Maker.id == maker_id).first()


def create_maker(db: Session, data: MakerCreate) -> Maker:
    m = Maker(name=data.name, is_active=True)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def update_maker(db: Session, maker: Maker, data: MakerUpdate) -> Maker:
    maker.name = data.name
    maker.is_active = data.is_active
    db.commit()
    db.refresh(maker)
    return maker


def deactivate_maker(db: Session, maker: Maker) -> None:
    maker.is_active = False
    db.commit()


# ---------------------------------------------------------------------------
# ディーラー × メーカー
# ---------------------------------------------------------------------------

def list_dealer_makers(db: Session, dealer_id: Optional[int] = None) -> list[DealerMakerOut]:
    q = (
        db.query(DealerMaker)
        .options(joinedload(DealerMaker.dealer), joinedload(DealerMaker.maker))
        .filter(DealerMaker.is_active.is_(True))
    )
    if dealer_id:
        q = q.filter(DealerMaker.dealer_id == dealer_id)
    rows = q.all()
    return [
        DealerMakerOut(
            id=r.id,
            dealer_id=r.dealer_id,
            maker_id=r.maker_id,
            dealer_name=r.dealer.name,
            maker_name=r.maker.name,
            is_active=r.is_active,
        )
        for r in rows
    ]


def create_dealer_maker(db: Session, data: DealerMakerCreate) -> DealerMaker:
    existing = (
        db.query(DealerMaker)
        .filter(
            DealerMaker.dealer_id == data.dealer_id,
            DealerMaker.maker_id == data.maker_id,
        )
        .first()
    )
    if existing:
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing
    dm = DealerMaker(dealer_id=data.dealer_id, maker_id=data.maker_id, is_active=True)
    db.add(dm)
    db.commit()
    db.refresh(dm)
    return dm


def deactivate_dealer_maker(db: Session, dm: DealerMaker) -> None:
    dm.is_active = False
    db.commit()


# ---------------------------------------------------------------------------
# 商品表示ヘルパー
# ---------------------------------------------------------------------------

def delivery_code_to_out(row) -> "ProductDeliveryCodeOut":
    from app.schemas import ProductDeliveryCodeOut

    return ProductDeliveryCodeOut(
        id=row.id,
        product_id=row.product_id,
        dealer_id=row.dealer_id,
        dealer_name=row.dealer.name if row.dealer else None,
        delivery_code=row.delivery_code,
        note=row.note,
        is_active=row.is_active,
    )


def product_to_out(
    db: Session,
    product: Product,
    include_delivery_codes: bool = False,
) -> ProductOut:
    from app import crud as crud_core

    codes = []
    if include_delivery_codes and product.delivery_codes is not None:
        codes = [
            delivery_code_to_out(c)
            for c in product.delivery_codes
            if c.is_active
        ]
    active_ids = crud_core.get_active_store_ids_for_product(db, product.id)
    stores = crud_core.get_stores(db, active_only=True)
    expand_all = bool(stores) and len(active_ids) == len(stores)
    return ProductOut(
        id=product.id,
        name=product.name,
        barcode=product.barcode,
        jan_code=product.jan_code,
        unit=product.unit,
        warning_threshold=product.warning_threshold,
        critical_threshold=product.critical_threshold,
        category_id=product.category_id,
        category_name=product.category.name if product.category else None,
        maker_id=product.maker_id,
        maker_name=product.maker.name if product.maker else None,
        dealer_id=product.dealer_id,
        dealer_name=product.dealer.name if product.dealer else None,
        delivery_codes=codes,
        expand_all_stores=expand_all,
        active_store_ids=active_ids,
    )


# ---------------------------------------------------------------------------
# ダッシュボード集計
# ---------------------------------------------------------------------------

def _summarize_category(db: Session, store_id: int, cat: Category) -> CategorySummaryOut:
    """is_active=true の商品のみ集計（アラート対象）"""
    rows = (
        db.query(Inventory)
        .options(joinedload(Inventory.product))
        .join(Product, Product.id == Inventory.product_id)
        .filter(
            Inventory.store_id == store_id,
            Inventory.is_active.is_(True),
            Product.category_id == cat.id,
        )
        .all()
    )
    settings_map = get_settings_map(db, store_id)
    yellow = red = 0
    for inv in rows:
        product = inv.product
        warning, critical = resolve_thresholds(
            product, settings_map.get(product.id)
        )
        level = calc_stock_level(inv.quantity, warning, critical)
        if level == "yellow":
            yellow += 1
        elif level == "red":
            red += 1
    return CategorySummaryOut(
        category_id=cat.id,
        category_name=cat.name,
        section=cat.section,
        total_sku=len(rows),
        yellow_count=yellow,
        red_count=red,
    )


def get_category_summaries(db: Session, store_id: int) -> list[CategorySummaryOut]:
    categories = get_categories(db, active_only=True)
    return [_summarize_category(db, store_id, cat) for cat in categories]


def get_dashboard_sections(db: Session, store_id: int) -> DashboardSectionsOut:
    materials = [
        _summarize_category(db, store_id, cat)
        for cat in get_categories(db, active_only=True, section=CategorySection.MATERIALS.value)
    ]
    retail = [
        _summarize_category(db, store_id, cat)
        for cat in get_categories(db, active_only=True, section=CategorySection.RETAIL.value)
    ]
    return DashboardSectionsOut(materials=materials, retail=retail)


# ---------------------------------------------------------------------------
# 発注・納品
# ---------------------------------------------------------------------------

def list_purchase_orders(
    db: Session,
    store_id: Optional[int] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> list[PurchaseOrderListItem]:
    q = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.store), joinedload(PurchaseOrder.dealer))
        .order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.id.desc())
    )
    if store_id:
        q = q.filter(PurchaseOrder.store_id == store_id)
    if year:
        q = q.filter(extract("year", PurchaseOrder.order_date) == year)
    if month:
        q = q.filter(extract("month", PurchaseOrder.order_date) == month)

    result = []
    for po in q.all():
        items = db.query(PurchaseOrderItem).filter(
            PurchaseOrderItem.purchase_order_id == po.id
        ).all()
        total = sum((i.unit_price or 0) * i.quantity for i in items)
        result.append(
            PurchaseOrderListItem(
                id=po.id,
                store_id=po.store_id,
                store_name=po.store.name,
                dealer_id=po.dealer_id,
                dealer_name=po.dealer.name,
                order_date=po.order_date,
                item_count=len(items),
                total_amount=total if total else None,
            )
        )
    return result


def get_purchase_order(db: Session, order_id: int) -> PurchaseOrderOut | None:
    po = (
        db.query(PurchaseOrder)
        .options(
            joinedload(PurchaseOrder.store),
            joinedload(PurchaseOrder.dealer),
            joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.product),
        )
        .filter(PurchaseOrder.id == order_id)
        .first()
    )
    if not po:
        return None
    items_out = [
        PurchaseOrderItemOut(
            id=i.id,
            product_id=i.product_id,
            product_name=i.product.name,
            barcode=i.product.barcode,
            quantity=i.quantity,
            unit_price=i.unit_price,
        )
        for i in po.items
    ]
    total = sum((i.unit_price or 0) * i.quantity for i in po.items)
    return PurchaseOrderOut(
        id=po.id,
        store_id=po.store_id,
        store_name=po.store.name,
        dealer_id=po.dealer_id,
        dealer_name=po.dealer.name,
        order_date=po.order_date,
        note=po.note,
        created_at=po.created_at,
        item_count=len(items_out),
        total_amount=total if total else None,
        items=items_out,
    )


def confirm_purchase_order(
    db: Session,
    user: User,
    store_id: int,
    dealer_id: int,
    order_date: date,
    lines: list[dict],
    note: Optional[str] = None,
) -> PurchaseOrderOut:
    """納品確定: 発注記録 + 在庫補充"""
    po = PurchaseOrder(
        store_id=store_id,
        dealer_id=dealer_id,
        order_date=order_date,
        note=note,
    )
    db.add(po)
    db.flush()

    for line in lines:
        product_id = int(line["product_id"])
        quantity = int(line["quantity"])
        unit_price = line.get("unit_price")
        db.add(
            PurchaseOrderItem(
                purchase_order_id=po.id,
                product_id=product_id,
                quantity=quantity,
                unit_price=int(unit_price) if unit_price is not None else None,
            )
        )
        inv = get_or_create_inventory(db, store_id, product_id, commit=False)
        inv.is_active = True
        inv.quantity += quantity
        db.add(
            InventoryLog(
                store_id=store_id,
                product_id=product_id,
                user_id=user.id,
                action=InventoryAction.RESTOCK,
                quantity_change=quantity,
                quantity_after=inv.quantity,
            )
        )

    db.commit()
    db.refresh(po)
    return get_purchase_order(db, po.id)


def dealer_monthly_totals(db: Session, year: int) -> list[dict]:
    """ディーラー別・月別発注金額"""
    rows = (
        db.query(
            Dealer.id,
            Dealer.name,
            extract("month", PurchaseOrder.order_date).label("month"),
            func.sum(PurchaseOrderItem.quantity * func.coalesce(PurchaseOrderItem.unit_price, 0)),
        )
        .join(PurchaseOrder, PurchaseOrder.dealer_id == Dealer.id)
        .join(PurchaseOrderItem, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .filter(extract("year", PurchaseOrder.order_date) == year)
        .group_by(Dealer.id, "month")
        .all()
    )
    return [
        {"dealer_id": r[0], "dealer_name": r[1], "month": int(r[2]), "amount": int(r[3] or 0)}
        for r in rows
    ]


def maker_monthly_quantities(db: Session, year: int) -> list[dict]:
    rows = (
        db.query(
            Maker.id,
            Maker.name,
            Category.name,
            extract("month", PurchaseOrder.order_date).label("month"),
            func.sum(PurchaseOrderItem.quantity),
        )
        .join(Product, Product.maker_id == Maker.id)
        .join(Category, Category.id == Product.category_id)
        .join(PurchaseOrderItem, PurchaseOrderItem.product_id == Product.id)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .filter(extract("year", PurchaseOrder.order_date) == year)
        .group_by(Maker.id, Category.name, "month")
        .all()
    )
    return [
        {
            "maker_id": r[0],
            "maker_name": r[1],
            "category_name": r[2],
            "month": int(r[3]),
            "quantity": int(r[4] or 0),
        }
        for r in rows
    ]
