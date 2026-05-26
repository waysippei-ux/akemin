"""
マスタ（カテゴリ・ディーラー・メーカー）と発注の CRUD
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from sqlalchemy import extract, func
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Brand,
    Category,
    Dealer,
    Section,
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
    DashboardSectionBlockOut,
    DashboardSectionsOut,
    SectionCreate,
    SectionOut,
    SectionUpdate,
    DealerCreate,
    DealerMakerCreate,
    DealerMakerOut,
    DealerOut,
    DealerUpdate,
    InventoryItemOut,
    BrandCreate,
    BrandOut,
    BrandUpdate,
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
# 棚（sections）
# ---------------------------------------------------------------------------

def get_sections(db: Session, active_only: bool = True) -> list[Section]:
    q = db.query(Section)
    if active_only:
        q = q.filter(Section.is_active.is_(True))
    return q.order_by(Section.sort_order, Section.id).all()


def get_section(db: Session, section_id: int) -> Section | None:
    return db.query(Section).filter(Section.id == section_id).first()


def count_categories_for_section(db: Session, section_id: int) -> int:
    return db.query(Category).filter(Category.section == section_id).count()


def section_to_out(db: Session, section: Section) -> SectionOut:
    return SectionOut(
        id=section.id,
        name=section.name,
        color=section.color,
        sort_order=section.sort_order,
        is_active=section.is_active,
        category_count=count_categories_for_section(db, section.id),
    )


def create_section(db: Session, data: SectionCreate) -> Section:
    max_order = db.query(func.max(Section.sort_order)).scalar() or 0
    sec = Section(
        name=data.name.strip(),
        color=(data.color or "#eae9fd").strip(),
        sort_order=max_order + 1,
        is_active=True,
    )
    db.add(sec)
    db.commit()
    db.refresh(sec)
    return sec


def update_section(db: Session, section: Section, data: SectionUpdate) -> Section:
    section.name = data.name.strip()
    section.color = data.color.strip()
    section.is_active = data.is_active
    db.commit()
    db.refresh(section)
    return section


def delete_section(db: Session, section: Section) -> None:
    if count_categories_for_section(db, section.id) > 0:
        raise ValueError("この棚にカテゴリが登録されています")
    db.delete(section)
    db.commit()


def get_section_names_map(db: Session) -> dict[int, str]:
    return {s.id: s.name for s in get_sections(db, active_only=False)}


# ---------------------------------------------------------------------------
# カテゴリ
# ---------------------------------------------------------------------------

def category_to_out(db: Session, cat: Category) -> CategoryOut:
    sec = get_section(db, cat.section)
    return CategoryOut(
        id=cat.id,
        name=cat.name,
        section=cat.section,
        section_name=sec.name if sec else None,
        sort_order=cat.sort_order,
        is_active=cat.is_active,
    )


def next_category_sort_order(db: Session, section_id: int) -> int:
    max_so = (
        db.query(func.max(Category.sort_order))
        .filter(Category.section == section_id)
        .scalar()
    )
    return (max_so or 0) + 1


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
    if not get_section(db, data.section):
        raise ValueError("指定された棚が見つかりません。")
    sort_order = data.sort_order or next_category_sort_order(db, data.section)
    cat = Category(
        name=data.name,
        section=data.section,
        sort_order=sort_order,
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


def count_products_for_category(db: Session, category_id: int) -> int:
    return (
        db.query(Product).filter(Product.category_id == category_id).count()
    )


def delete_category(db: Session, cat: Category) -> None:
    """商品未紐づけのカテゴリのみ物理削除"""
    if count_products_for_category(db, cat.id) > 0:
        raise ValueError("このカテゴリには商品が登録されています")
    db.delete(cat)
    db.commit()


def reorder_category(
    db: Session, cat: Category, direction: Literal["up", "down"]
) -> Category:
    """同一棚内で sort_order を入れ替え"""
    siblings = (
        db.query(Category)
        .filter(Category.section == cat.section)
        .order_by(Category.sort_order, Category.id)
        .all()
    )
    idx = next((i for i, c in enumerate(siblings) if c.id == cat.id), -1)
    if idx < 0:
        return cat
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if swap_idx < 0 or swap_idx >= len(siblings):
        return cat
    other = siblings[swap_idx]
    cat.sort_order, other.sort_order = other.sort_order, cat.sort_order
    db.commit()
    db.refresh(cat)
    return cat


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


def count_products_for_dealer(db: Session, dealer_id: int) -> int:
    from app.models import ProductDeliveryCode

    product_n = (
        db.query(Product).filter(Product.dealer_id == dealer_id).count()
    )
    code_n = (
        db.query(ProductDeliveryCode)
        .filter(ProductDeliveryCode.dealer_id == dealer_id)
        .count()
    )
    return product_n + code_n


def delete_dealer(db: Session, dealer: Dealer) -> None:
    if count_products_for_dealer(db, dealer.id) > 0:
        raise ValueError("このディーラーには商品が登録されています")
    db.delete(dealer)
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


def count_products_for_maker(db: Session, maker_id: int) -> int:
    return db.query(Product).filter(Product.maker_id == maker_id).count()


def delete_maker(db: Session, maker: Maker) -> None:
    if count_products_for_maker(db, maker.id) > 0:
        raise ValueError("このメーカーには商品が登録されています")
    db.query(Brand).filter(Brand.maker_id == maker.id).delete()
    db.delete(maker)
    db.commit()


# ---------------------------------------------------------------------------
# ブランド
# ---------------------------------------------------------------------------

def brand_to_out(brand: Brand, maker_name: str | None = None) -> BrandOut:
    return BrandOut(
        id=brand.id,
        name=brand.name,
        maker_id=brand.maker_id,
        maker_name=maker_name or (brand.maker.name if brand.maker else None),
        sort_order=brand.sort_order,
    )


def get_brands(
    db: Session, *, maker_id: int | None = None, active_maker_only: bool = True
) -> list[Brand]:
    q = db.query(Brand).options(joinedload(Brand.maker))
    if maker_id is not None:
        q = q.filter(Brand.maker_id == maker_id)
    if active_maker_only:
        q = q.join(Maker).filter(Maker.is_active.is_(True))
    return q.order_by(Brand.sort_order, Brand.name).all()


def get_brand(db: Session, brand_id: int) -> Brand | None:
    return (
        db.query(Brand)
        .options(joinedload(Brand.maker))
        .filter(Brand.id == brand_id)
        .first()
    )


def create_brand(db: Session, data: BrandCreate) -> Brand:
    maker = get_maker(db, data.maker_id)
    if not maker:
        raise ValueError("メーカーが見つかりません")
    if data.sort_order <= 0:
        max_order = (
            db.query(func.max(Brand.sort_order))
            .filter(Brand.maker_id == data.maker_id)
            .scalar()
        )
        sort_order = (max_order or 0) + 1
    else:
        sort_order = data.sort_order
    brand = Brand(name=data.name, maker_id=data.maker_id, sort_order=sort_order)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


def update_brand(db: Session, brand: Brand, data: BrandUpdate) -> Brand:
    maker = get_maker(db, data.maker_id)
    if not maker:
        raise ValueError("メーカーが見つかりません")
    brand.name = data.name
    brand.maker_id = data.maker_id
    brand.sort_order = data.sort_order
    db.commit()
    db.refresh(brand)
    return brand


def delete_brand(db: Session, brand: Brand) -> None:
    db.delete(brand)
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


def format_product_deployment(
    active_ids: list[int],
    expand_all: bool,
    stores: list,
) -> tuple[str, list[str]]:
    """展開店舗の表示ラベルと店舗名一覧"""
    if expand_all:
        return "全店舗", [s.name for s in stores]
    if not active_ids:
        return "未配置", []
    name_by_id = {s.id: s.name for s in stores}
    names = sorted(name_by_id[i] for i in active_ids if i in name_by_id)
    if not names:
        return "未配置", []
    if len(names) == 1:
        return names[0], names
    return f"{names[0]} 他{len(names) - 1}店舗", names


def product_to_out(
    db: Session,
    product: Product,
    include_delivery_codes: bool = False,
    stores: list | None = None,
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
    if stores is None:
        stores = crud_core.get_stores(db, active_only=True)
    expand_all = bool(stores) and len(active_ids) == len(stores)
    deployment_label, active_store_names = format_product_deployment(
        active_ids, expand_all, stores
    )
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
        active_store_names=active_store_names,
        deployment_label=deployment_label,
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
    blocks: list[DashboardSectionBlockOut] = []
    for sec in get_sections(db, active_only=True):
        cats = get_categories(db, active_only=True, section=sec.id)
        blocks.append(
            DashboardSectionBlockOut(
                section_id=sec.id,
                section_name=sec.name,
                color=sec.color,
                sort_order=sec.sort_order,
                categories=[_summarize_category(db, store_id, cat) for cat in cats],
            )
        )
    return DashboardSectionsOut(sections=blocks)


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
