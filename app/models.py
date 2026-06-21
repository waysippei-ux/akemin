"""
データベースのテーブル定義（SQLAlchemy モデル）

拡張方針:
- マスタ系は is_active で論理削除（物理削除しない）
- 店舗・ディーラー・メーカー・カテゴリは管理画面から追加可能
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    STAFF = "staff"


class InventoryAction(str, enum.Enum):
    USE = "use"
    RESTOCK = "restock"


class CategorySection(int, enum.Enum):
    """ダッシュボード TOP のセクション区分"""
    MATERIALS = 1   # サロンで使う材料在庫
    RETAIL = 2      # 店で販売する商品在庫


# ---------------------------------------------------------------------------
# 既存テーブル（列の追加のみ — 下記 Product を参照）
# ---------------------------------------------------------------------------


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="store")
    inventories: Mapped[list["Inventory"]] = relationship(back_populates="store")
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="store")
    ordering_items: Mapped[list["OrderingItem"]] = relationship(back_populates="store")
    product_settings: Mapped[list["StoreProductSetting"]] = relationship(back_populates="store")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    store_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stores.id"), nullable=True)

    store: Mapped[Optional["Store"]] = relationship(back_populates="users")
    inventory_logs: Mapped[list["InventoryLog"]] = relationship(
        "InventoryLog",
        foreign_keys="[InventoryLog.user_id]",
        back_populates="user",
    )


# ---------------------------------------------------------------------------
# マスタ（新規）
# ---------------------------------------------------------------------------


class Section(Base):
    """棚（ダッシュボードの大区分・材料/店販など）"""
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#eae9fd", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    categories: Mapped[list["Category"]] = relationship(back_populates="shelf_section")


class Category(Base):
    """商品カテゴリ（所属棚 = sections.id）"""
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    section: Mapped[int] = mapped_column(
        ForeignKey("sections.id"),
        default=CategorySection.MATERIALS.value,
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    shelf_section: Mapped["Section"] = relationship(back_populates="categories")

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Dealer(Base):
    """仕入先ディーラー"""
    __tablename__ = "dealers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    dealer_makers: Mapped[list["DealerMaker"]] = relationship(back_populates="dealer")
    products: Mapped[list["Product"]] = relationship(back_populates="dealer")
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="dealer")
    product_delivery_codes: Mapped[list["ProductDeliveryCode"]] = relationship(
        back_populates="dealer"
    )


class Maker(Base):
    """メーカー"""
    __tablename__ = "makers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    dealer_makers: Mapped[list["DealerMaker"]] = relationship(back_populates="maker")
    brands: Mapped[list["Brand"]] = relationship(back_populates="maker", cascade="all, delete-orphan")
    products: Mapped[list["Product"]] = relationship(back_populates="maker")


class Brand(Base):
    """ブランド（メーカー配下）"""
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    maker_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("makers.id"), nullable=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    maker: Mapped[Optional["Maker"]] = relationship(back_populates="brands")
    products: Mapped[list["Product"]] = relationship(back_populates="brand")


class DealerMaker(Base):
    """ディーラー × メーカー（多対多・取扱関係）"""
    __tablename__ = "dealer_makers"
    __table_args__ = (UniqueConstraint("dealer_id", "maker_id", name="uq_dealer_maker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dealer_id: Mapped[int] = mapped_column(ForeignKey("dealers.id"), nullable=False)
    maker_id: Mapped[int] = mapped_column(ForeignKey("makers.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    dealer: Mapped["Dealer"] = relationship(back_populates="dealer_makers")
    maker: Mapped["Maker"] = relationship(back_populates="dealer_makers")


# ---------------------------------------------------------------------------
# 商品（既存 + 列追加）
# ---------------------------------------------------------------------------


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    barcode: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    jan_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    unit: Mapped[str] = mapped_column(String(20), default="本")
    standard_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_threshold: Mapped[int] = mapped_column(Integer, default=5)
    critical_threshold: Mapped[int] = mapped_column(Integer, default=2)

    # --- 追加列（マスタ参照）---
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False, index=True)
    maker_id: Mapped[Optional[int]] = mapped_column(ForeignKey("makers.id"), nullable=True, index=True)
    dealer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dealers.id"), nullable=True, index=True)
    brand_id: Mapped[Optional[int]] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)

    category: Mapped["Category"] = relationship(back_populates="products")
    maker: Mapped[Optional["Maker"]] = relationship(back_populates="products")
    dealer: Mapped[Optional["Dealer"]] = relationship(back_populates="products")
    brand: Mapped[Optional["Brand"]] = relationship(back_populates="products")
    inventories: Mapped[list["Inventory"]] = relationship(back_populates="product")
    inventory_logs: Mapped[list["InventoryLog"]] = relationship(back_populates="product")
    purchase_order_items: Mapped[list["PurchaseOrderItem"]] = relationship(back_populates="product")
    ordering_items: Mapped[list["OrderingItem"]] = relationship(back_populates="product")
    delivery_codes: Mapped[list["ProductDeliveryCode"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )
    store_settings: Mapped[list["StoreProductSetting"]] = relationship(back_populates="product")


class ProductDeliveryCode(Base):
    """ディーラー別の納品コード（1商品 × 複数ディーラー）"""
    __tablename__ = "product_delivery_codes"
    __table_args__ = (
        UniqueConstraint("dealer_id", "delivery_code", name="uq_dealer_delivery_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    dealer_id: Mapped[int] = mapped_column(ForeignKey("dealers.id"), nullable=False, index=True)
    delivery_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(JST)
    )

    product: Mapped["Product"] = relationship(back_populates="delivery_codes")
    dealer: Mapped["Dealer"] = relationship(back_populates="product_delivery_codes")


# ---------------------------------------------------------------------------
# 在庫（既存・変更なし）
# ---------------------------------------------------------------------------


class Inventory(Base):
    __tablename__ = "inventories"
    __table_args__ = (UniqueConstraint("store_id", "product_id", name="uq_store_product"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    store: Mapped["Store"] = relationship(back_populates="inventories")
    product: Mapped["Product"] = relationship(back_populates="inventories")


class InventoryLog(Base):
    __tablename__ = "inventory_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[InventoryAction] = mapped_column(Enum(InventoryAction), nullable=False)
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(JST)
    )
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    edited_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    original_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    edit_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="[InventoryLog.user_id]",
        back_populates="inventory_logs",
    )
    product: Mapped["Product"] = relationship(back_populates="inventory_logs")
    editor: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="[InventoryLog.edited_by]",
    )
    edits: Mapped[list["InventoryLogEdit"]] = relationship(
        back_populates="log", cascade="all, delete-orphan"
    )


class InventoryLogEdit(Base):
    __tablename__ = "inventory_log_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    log_id: Mapped[int] = mapped_column(ForeignKey("inventory_logs.id"), nullable=False, index=True)
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(JST), nullable=False
    )
    edited_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    before_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    after_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    edit_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    log: Mapped["InventoryLog"] = relationship(back_populates="edits")
    editor: Mapped["User"] = relationship(foreign_keys=[edited_by])


# ---------------------------------------------------------------------------
# 発注・納品（新規）
# ---------------------------------------------------------------------------


class PurchaseOrder(Base):
    """納品書1枚 = 1レコード"""
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    dealer_id: Mapped[int] = mapped_column(ForeignKey("dealers.id"), nullable=False, index=True)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(JST)
    )

    store: Mapped["Store"] = relationship(back_populates="purchase_orders")
    dealer: Mapped["Dealer"] = relationship(back_populates="purchase_orders")
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
    )


class PurchaseOrderItem(Base):
    """納品書の明細行"""
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 円

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="purchase_order_items")


class OrderingItem(Base):
    """発注中管理（登録ごとに別レコード。同一商品の複数回発注を保持）"""
    __tablename__ = "ordering_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    ordered_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(JST)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(JST),
        onupdate=lambda: datetime.now(JST),
    )

    store: Mapped["Store"] = relationship(back_populates="ordering_items")
    product: Mapped["Product"] = relationship(back_populates="ordering_items")


# -----------------------------------------------------------------------
# 店舗別発注目安設定
# -----------------------------------------------------------------------
class StoreProductSetting(Base):
    __tablename__ = "store_product_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    warning_threshold: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    critical_threshold: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    standard_stock: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    store: Mapped["Store"] = relationship(back_populates="product_settings")
    product: Mapped["Product"] = relationship(back_populates="store_settings")

    __table_args__ = (
        UniqueConstraint("store_id", "product_id", name="uq_store_product_setting"),
    )
