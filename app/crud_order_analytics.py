"""
発注データ分析用クエリ
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.models import (
    Category,
    CategorySection,
    Dealer,
    Maker,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Store,
)

SECTION_NAMES = {
    CategorySection.MATERIALS.value: "材料の棚",
    CategorySection.RETAIL.value: "店販の棚",
}

LINE_AMOUNT = PurchaseOrderItem.quantity * func.coalesce(PurchaseOrderItem.unit_price, 0)


@dataclass
class OrderFilter:
    year: Optional[int] = None
    month: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    store_id: Optional[int] = None
    section: Optional[int] = None
    category_id: Optional[int] = None
    dealer_id: Optional[int] = None
    maker_id: Optional[int] = None


def _apply_filters(q, f: OrderFilter):
    if f.date_from:
        q = q.filter(PurchaseOrder.order_date >= f.date_from)
    if f.date_to:
        q = q.filter(PurchaseOrder.order_date <= f.date_to)
    if f.year and not f.date_from:
        q = q.filter(extract("year", PurchaseOrder.order_date) == f.year)
    if f.month and not f.date_from:
        q = q.filter(extract("month", PurchaseOrder.order_date) == f.month)
    if f.store_id:
        q = q.filter(PurchaseOrder.store_id == f.store_id)
    if f.section:
        q = q.filter(Category.section == f.section)
    if f.category_id:
        q = q.filter(Product.category_id == f.category_id)
    if f.dealer_id:
        q = q.filter(PurchaseOrder.dealer_id == f.dealer_id)
    if f.maker_id:
        q = q.filter(Product.maker_id == f.maker_id)
    return q


def _base_line_query(db: Session, f: OrderFilter):
    q = (
        db.query(
            PurchaseOrder.id.label("order_id"),
            PurchaseOrder.order_date.label("order_date"),
            Store.id.label("store_id"),
            Store.name.label("store_name"),
            Dealer.id.label("dealer_id"),
            Dealer.name.label("dealer_name"),
            Category.id.label("category_id"),
            Category.name.label("category_name"),
            Category.section.label("section"),
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Product.barcode.label("barcode"),
            Product.unit.label("unit"),
            Maker.id.label("maker_id"),
            Maker.name.label("maker_name"),
            PurchaseOrderItem.quantity.label("quantity"),
            PurchaseOrderItem.unit_price.label("unit_price"),
            LINE_AMOUNT.label("amount"),
        )
        .select_from(PurchaseOrderItem)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .join(Store, Store.id == PurchaseOrder.store_id)
        .join(Dealer, Dealer.id == PurchaseOrder.dealer_id)
        .join(Product, Product.id == PurchaseOrderItem.product_id)
        .join(Category, Category.id == Product.category_id)
        .outerjoin(Maker, Maker.id == Product.maker_id)
    )
    return _apply_filters(q, f)


def has_order_data(db: Session, f: OrderFilter) -> bool:
    return _base_line_query(db, f).limit(1).first() is not None


def get_summary(db: Session, f: OrderFilter) -> dict:
    sub = _base_line_query(db, f).subquery()
    row = db.query(
        func.coalesce(func.sum(sub.c.amount), 0),
        func.coalesce(func.sum(sub.c.quantity), 0),
        func.count(func.distinct(sub.c.order_id)),
        func.count(func.distinct(sub.c.product_id)),
    ).one()
    return {
        "total_amount": int(row[0]),
        "total_quantity": int(row[1]),
        "order_count": int(row[2]),
        "sku_count": int(row[3]),
        "has_data": bool(row[2]),
    }


def _ratio(amount: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(amount * 1000 / total) / 10


def get_by_store(db: Session, f: OrderFilter) -> list[dict]:
    sub = _base_line_query(db, f).subquery()
    rows = (
        db.query(
            sub.c.store_id,
            sub.c.store_name,
            func.sum(sub.c.amount),
            func.sum(sub.c.quantity),
            func.count(func.distinct(sub.c.order_id)),
        )
        .group_by(sub.c.store_id, sub.c.store_name)
        .order_by(func.sum(sub.c.amount).desc())
        .all()
    )
    return [
        {
            "store_id": r[0],
            "store_name": r[1],
            "amount": int(r[2] or 0),
            "quantity": int(r[3] or 0),
            "order_count": int(r[4] or 0),
        }
        for r in rows
    ]


def get_by_section(db: Session, f: OrderFilter) -> list[dict]:
    sub = _base_line_query(db, f).subquery()
    rows = (
        db.query(
            sub.c.section,
            func.sum(sub.c.amount),
            func.sum(sub.c.quantity),
            func.count(func.distinct(sub.c.order_id)),
        )
        .group_by(sub.c.section)
        .order_by(sub.c.section)
        .all()
    )
    total = sum(int(r[1] or 0) for r in rows)
    return [
        {
            "section": int(r[0]),
            "section_name": SECTION_NAMES.get(int(r[0]), f"区分{r[0]}"),
            "amount": int(r[1] or 0),
            "quantity": int(r[2] or 0),
            "order_count": int(r[3] or 0),
            "ratio_percent": _ratio(int(r[1] or 0), total),
        }
        for r in rows
    ]


def get_by_category(db: Session, f: OrderFilter) -> list[dict]:
    sub = _base_line_query(db, f).subquery()
    rows = (
        db.query(
            sub.c.category_id,
            sub.c.category_name,
            sub.c.section,
            func.sum(sub.c.amount),
            func.sum(sub.c.quantity),
        )
        .group_by(sub.c.category_id, sub.c.category_name, sub.c.section)
        .order_by(func.sum(sub.c.amount).desc())
        .all()
    )
    total = sum(int(r[3] or 0) for r in rows)
    return [
        {
            "category_id": r[0],
            "category_name": r[1],
            "section": int(r[2]),
            "section_name": SECTION_NAMES.get(int(r[2]), ""),
            "amount": int(r[3] or 0),
            "quantity": int(r[4] or 0),
            "ratio_percent": _ratio(int(r[3] or 0), total),
        }
        for r in rows
    ]


def get_by_dealer(db: Session, f: OrderFilter) -> list[dict]:
    sub = _base_line_query(db, f).subquery()
    rows = (
        db.query(
            sub.c.dealer_id,
            sub.c.dealer_name,
            func.sum(sub.c.amount),
            func.sum(sub.c.quantity),
            func.count(func.distinct(sub.c.maker_id)),
        )
        .group_by(sub.c.dealer_id, sub.c.dealer_name)
        .order_by(func.sum(sub.c.amount).desc())
        .all()
    )
    total = sum(int(r[2] or 0) for r in rows)
    return [
        {
            "dealer_id": r[0],
            "dealer_name": r[1],
            "amount": int(r[2] or 0),
            "quantity": int(r[3] or 0),
            "maker_count": int(r[4] or 0),
            "ratio_percent": _ratio(int(r[2] or 0), total),
        }
        for r in rows
    ]


def get_by_maker(db: Session, f: OrderFilter) -> list[dict]:
    sub = _base_line_query(db, f).subquery()
    rows = (
        db.query(
            sub.c.maker_id,
            sub.c.maker_name,
            func.min(sub.c.dealer_name),
            func.count(func.distinct(sub.c.dealer_id)),
            func.sum(sub.c.amount),
            func.sum(sub.c.quantity),
        )
        .filter(sub.c.maker_id.isnot(None))
        .group_by(sub.c.maker_id, sub.c.maker_name)
        .order_by(func.sum(sub.c.amount).desc())
        .all()
    )
    total = sum(int(r[4] or 0) for r in rows)
    out = []
    for r in rows:
        dealer_label = r[2] or "—"
        if int(r[3] or 0) > 1:
            dealer_label = "複数"
        out.append(
            {
                "maker_id": r[0],
                "maker_name": r[1] or "（未設定）",
                "dealer_name": dealer_label,
                "amount": int(r[4] or 0),
                "quantity": int(r[5] or 0),
                "ratio_percent": _ratio(int(r[4] or 0), total),
            }
        )
    return out


def get_history(db: Session, f: OrderFilter) -> list[dict]:
    sub = _base_line_query(db, f).subquery()
    rows = (
        db.query(
            sub.c.order_id,
            sub.c.order_date,
            sub.c.store_name,
            sub.c.dealer_name,
            func.count(sub.c.product_id),
            func.sum(sub.c.amount),
        )
        .group_by(
            sub.c.order_id,
            sub.c.order_date,
            sub.c.store_name,
            sub.c.dealer_name,
        )
        .order_by(sub.c.order_date.desc(), sub.c.order_id.desc())
        .all()
    )
    return [
        {
            "order_id": r[0],
            "order_date": r[1].isoformat() if r[1] else "",
            "store_name": r[2],
            "dealer_name": r[3],
            "item_count": int(r[4] or 0),
            "total_amount": int(r[5] or 0),
        }
        for r in rows
    ]


def get_order_detail_lines(db: Session, order_id: int) -> list[dict]:
    rows = (
        db.query(
            Product.barcode,
            Product.name,
            PurchaseOrderItem.quantity,
            PurchaseOrderItem.unit_price,
            LINE_AMOUNT,
        )
        .join(Product, Product.id == PurchaseOrderItem.product_id)
        .filter(PurchaseOrderItem.purchase_order_id == order_id)
        .all()
    )
    return [
        {
            "product_code": r[0],
            "product_name": r[1],
            "quantity": r[2],
            "unit_price": r[3],
            "amount": int(r[4] or 0),
        }
        for r in rows
    ]


def _detail_line_query(db: Session, f: Optional[OrderFilter] = None):
    q = (
        db.query(
            PurchaseOrder.order_date.label("order_date"),
            Store.name.label("store_name"),
            Category.section.label("section"),
            Category.name.label("category_name"),
            Dealer.name.label("dealer_name"),
            Maker.name.label("maker_name"),
            Product.barcode.label("barcode"),
            Product.name.label("product_name"),
            PurchaseOrderItem.quantity.label("quantity"),
            PurchaseOrderItem.unit_price.label("unit_price"),
            LINE_AMOUNT.label("amount"),
        )
        .select_from(PurchaseOrderItem)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .join(Store, Store.id == PurchaseOrder.store_id)
        .join(Dealer, Dealer.id == PurchaseOrder.dealer_id)
        .join(Product, Product.id == PurchaseOrderItem.product_id)
        .join(Category, Category.id == Product.category_id)
        .outerjoin(Maker, Maker.id == Product.maker_id)
    )
    if f:
        q = _apply_filters(q, f)
    return q.order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.id.desc())


def iter_detail_csv_rows(db: Session, f: Optional[OrderFilter] = None) -> list[list]:
    """明細CSV用の行（ヘッダー含む）"""
    header = [
        "日付",
        "店舗名",
        "区分",
        "カテゴリ名",
        "ディーラー名",
        "メーカー名",
        "商品コード",
        "商品名",
        "数量",
        "単価",
        "金額",
    ]
    rows_out = [header]
    for r in _detail_line_query(db, f).all():
        m = r._mapping
        rows_out.append(
            [
                m["order_date"].isoformat() if m["order_date"] else "",
                m["store_name"],
                SECTION_NAMES.get(int(m["section"]), ""),
                m["category_name"],
                m["dealer_name"],
                m["maker_name"] or "",
                m["barcode"],
                m["product_name"],
                m["quantity"],
                m["unit_price"] if m["unit_price"] is not None else "",
                int(m["amount"] or 0),
            ]
        )
    return rows_out


TAB_LABELS = {
    "store": "店舗別",
    "section": "区分別",
    "category": "カテゴリ別",
    "dealer": "ディーラー別",
    "maker": "メーカー別",
    "history": "発注履歴",
}


def build_tab_csv_rows(db: Session, tab: str, f: OrderFilter) -> list[list]:
    if tab == "store":
        rows = [["店舗名", "発注金額", "発注数量", "発注件数"]]
        for r in get_by_store(db, f):
            rows.append([r["store_name"], r["amount"], r["quantity"], r["order_count"]])
        return rows
    if tab == "section":
        rows = [["区分名", "発注金額", "発注数量", "割合(%)"]]
        for r in get_by_section(db, f):
            rows.append([r["section_name"], r["amount"], r["quantity"], r["ratio_percent"]])
        return rows
    if tab == "category":
        rows = [["カテゴリ名", "区分", "発注金額", "発注数量", "割合(%)"]]
        for r in get_by_category(db, f):
            rows.append(
                [
                    r["category_name"],
                    r["section_name"],
                    r["amount"],
                    r["quantity"],
                    r["ratio_percent"],
                ]
            )
        return rows
    if tab == "dealer":
        rows = [["ディーラー名", "発注金額", "発注数量", "取扱メーカー数", "割合(%)"]]
        for r in get_by_dealer(db, f):
            rows.append(
                [
                    r["dealer_name"],
                    r["amount"],
                    r["quantity"],
                    r["maker_count"],
                    r["ratio_percent"],
                ]
            )
        return rows
    if tab == "maker":
        rows = [["メーカー名", "ディーラー名", "発注金額", "発注数量", "割合(%)"]]
        for r in get_by_maker(db, f):
            rows.append(
                [
                    r["maker_name"],
                    r["dealer_name"],
                    r["amount"],
                    r["quantity"],
                    r["ratio_percent"],
                ]
            )
        return rows
    if tab == "history":
        rows = [["日付", "店舗", "ディーラー", "商品点数", "合計金額"]]
        for r in get_history(db, f):
            rows.append(
                [
                    r["order_date"],
                    r["store_name"],
                    r["dealer_name"],
                    r["item_count"],
                    r["total_amount"],
                ]
            )
        return rows
    raise ValueError(f"Unknown tab: {tab}")


def build_csv_string(rows: list[list]) -> str:
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerows(rows)
    return buf.getvalue()
