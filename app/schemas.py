"""
API のリクエスト・レスポンスの型定義（Pydantic）
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models import InventoryAction, UserRole

# 在庫の色分け（ダッシュボード用）
StockLevel = Literal["green", "yellow", "red"]


# ---------------------------------------------------------------------------
# 認証
# ---------------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: UserRole
    store_id: Optional[int] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# 店舗
# ---------------------------------------------------------------------------

class StoreOut(BaseModel):
    id: int
    name: str
    is_active: bool = True

    model_config = {"from_attributes": True}


class StoreCreate(BaseModel):
    name: str


class StoreUpdate(BaseModel):
    name: str
    is_active: bool = True


class StoreProductSettingRowOut(BaseModel):
    """店舗別発注目安 — 商品1行（一覧・編集画面用）"""
    store_id: int
    store_name: str
    product_id: int
    product_name: str
    barcode: str
    category_id: int
    category_name: str = ""
    maker_id: Optional[int] = None
    maker_name: Optional[str] = None
    dealer_id: Optional[int] = None
    dealer_name: Optional[str] = None
    unit: str = "本"
    default_warning_threshold: int
    default_critical_threshold: int
    effective_warning_threshold: int
    effective_critical_threshold: int
    custom_warning_threshold: Optional[int] = None
    custom_critical_threshold: Optional[int] = None
    has_custom_setting: bool = False
    setting_id: Optional[int] = None


class StoreProductSettingUpsert(BaseModel):
    warning_threshold: int = Field(ge=0)
    critical_threshold: int = Field(ge=0)


# ---------------------------------------------------------------------------
# 商品（カラー材）
# ---------------------------------------------------------------------------

class ProductDeliveryCodeOut(BaseModel):
    id: int
    product_id: int
    dealer_id: int
    dealer_name: Optional[str] = None
    delivery_code: str
    note: Optional[str] = None
    is_active: bool = True

    model_config = {"from_attributes": True}


class ProductDeliveryCodeCreate(BaseModel):
    dealer_id: int
    delivery_code: str
    note: Optional[str] = None


class ProductDeploymentIn(BaseModel):
    """店舗への展開（inventories.is_active）"""
    expand_all_stores: bool = True
    store_ids: list[int] = Field(default_factory=list)


class ProductOut(BaseModel):
    id: int
    name: str
    barcode: str
    jan_code: Optional[str] = None
    unit: str
    warning_threshold: int
    critical_threshold: int
    category_id: int
    category_name: Optional[str] = None
    maker_id: Optional[int] = None
    maker_name: Optional[str] = None
    dealer_id: Optional[int] = None
    dealer_name: Optional[str] = None
    delivery_codes: list[ProductDeliveryCodeOut] = []
    expand_all_stores: bool = True
    active_store_ids: list[int] = Field(default_factory=list)
    active_store_names: list[str] = Field(default_factory=list)
    deployment_label: str = ""

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    name: str
    barcode: str
    category_id: int
    jan_code: Optional[str] = None
    unit: str = "本"
    warning_threshold: int = 5
    critical_threshold: int = 2
    maker_id: Optional[int] = None
    dealer_id: Optional[int] = None
    deployment: ProductDeploymentIn = Field(default_factory=ProductDeploymentIn)


class ProductUpdate(BaseModel):
    name: str
    barcode: str
    category_id: int
    jan_code: Optional[str] = None
    unit: str = "本"
    warning_threshold: int = Field(ge=0)
    critical_threshold: int = Field(ge=0)
    maker_id: Optional[int] = None
    dealer_id: Optional[int] = None
    deployment: ProductDeploymentIn = Field(default_factory=ProductDeploymentIn)


class ProductImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = []


# ---------------------------------------------------------------------------
# 在庫
# ---------------------------------------------------------------------------

class InventoryItemOut(BaseModel):
    """ダッシュボード1行分（商品情報 + 在庫 + 色）"""
    product_id: int
    product_name: str
    barcode: str
    unit: str
    quantity: int
    stock_level: StockLevel
    warning_threshold: int
    critical_threshold: int
    category_id: int
    category_name: str = ""
    maker_id: Optional[int] = None
    maker_name: Optional[str] = None
    dealer_id: Optional[int] = None
    dealer_name: Optional[str] = None
    is_on_shelf: bool = False


class InventoryScanRequest(BaseModel):
    """バーコードスキャン時の入力"""
    barcode: str
    action: InventoryAction
    quantity: int = Field(default=1, ge=1, description="増減する数量")
    store_id: int = Field(gt=0, description="店舗ID（必須）")
    recorded_at: Optional[datetime] = None


class StockRegisterRequest(BaseModel):
    """棚補充・使用登録（商品ID指定）"""
    store_id: int = Field(gt=0, description="店舗ID（必須）")
    product_id: int
    action: InventoryAction
    quantity: int = Field(ge=1)
    recorded_at: Optional[datetime] = None


class StockReplenishRequest(BaseModel):
    """棚補充登録"""
    store_id: int = Field(gt=0, description="店舗ID（必須）")
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1)
    recorded_at: Optional[datetime] = None


class StockConsumeRequest(BaseModel):
    """使用済み登録（在庫減）"""
    store_id: int = Field(gt=0, description="店舗ID（必須）")
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1)
    recorded_at: Optional[datetime] = None


class StockRegisterWithProductRequest(BaseModel):
    """未登録商品を新規登録してから棚に反映"""
    store_id: int = Field(gt=0, description="店舗ID（必須）")
    action: InventoryAction
    quantity: int = Field(ge=1)
    recorded_at: Optional[datetime] = None
    product: ProductCreate


class StockBulkLineIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)
    recorded_at: Optional[datetime] = None


class StockBulkRegisterRequest(BaseModel):
    store_id: int = Field(gt=0, description="店舗ID（必須）")
    action: InventoryAction
    lines: list[StockBulkLineIn]


class StockQuantityOut(BaseModel):
    """店舗×商品の現在庫（モーダル表示用）"""
    store_id: int
    product_id: int
    quantity: int
    unit: str = "本"
    is_on_shelf: bool = False


class StockLookupOut(BaseModel):
    code: str
    found: bool
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    barcode: Optional[str] = None
    unit: Optional[str] = None
    quantity: int = 0
    category_id: Optional[int] = None
    is_on_shelf: bool = False


# 増減ログに基づく分析（発注データ分析画面）
class StorePopularityRowOut(BaseModel):
    store_id: int
    store_name: str
    product_id: int
    product_name: str
    use_count: int
    use_quantity: int
    rank: int = 0


class StagnantProductRowOut(BaseModel):
    store_id: int
    store_name: str
    product_id: int
    product_name: str
    quantity: int
    unit: str = "本"
    days_without_movement: int


class StoreAssortmentRowOut(BaseModel):
    store_id: int
    store_name: str
    active_sku_count: int
    category_breakdown: dict[str, int] = Field(default_factory=dict)


class InventoryAnalyticsOut(BaseModel):
    popularity: list[StorePopularityRowOut] = []
    stagnant: list[StagnantProductRowOut] = []
    assortment: list[StoreAssortmentRowOut] = []


class StockBulkParseLineOut(BaseModel):
    product_code: str
    quantity: int
    matched: bool
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    unit: str = "本"
    current_quantity: int = 0


class StockBulkParseResult(BaseModel):
    lines: list[StockBulkParseLineOut] = []
    note: Optional[str] = None


class InventoryScanResponse(BaseModel):
    product_name: str
    action: InventoryAction
    quantity_change: int
    quantity_after: int
    stock_level: StockLevel
    message: str


class InventoryLogOut(BaseModel):
    id: int
    store_id: int
    product_id: int
    product_name: str
    action: InventoryAction
    quantity_change: int
    quantity_after: int
    username: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# AI 在庫分析
# ---------------------------------------------------------------------------

class AnalysisRequest(BaseModel):
    store_id: int


class AnalysisResponse(BaseModel):
    store_id: int
    store_name: str
    category_id: Optional[int] = None
    advice: str


# ---------------------------------------------------------------------------
# カテゴリ・ディーラー・メーカー
# ---------------------------------------------------------------------------

class SectionOut(BaseModel):
    id: int
    name: str
    color: str
    sort_order: int
    is_active: bool = True
    category_count: int = 0

    model_config = {"from_attributes": True}


class SectionCreate(BaseModel):
    name: str
    color: str = "#eae9fd"


class SectionUpdate(BaseModel):
    name: str
    color: str
    is_active: bool = True


class CategoryOut(BaseModel):
    id: int
    name: str
    section: int
    section_name: Optional[str] = None
    sort_order: int
    is_active: bool

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str
    section: int = Field(gt=0, description="所属する棚（sections.id）")
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str
    section: int = Field(gt=0)
    sort_order: int = 0
    is_active: bool = True


class CategoryOrderUpdate(BaseModel):
    direction: Literal["up", "down"]


class DealerOut(BaseModel):
    id: int
    name: str
    contact_info: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


class DealerCreate(BaseModel):
    name: str
    contact_info: Optional[str] = None


class DealerUpdate(BaseModel):
    name: str
    contact_info: Optional[str] = None
    is_active: bool = True


class MakerOut(BaseModel):
    id: int
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


class MakerCreate(BaseModel):
    name: str


class MakerUpdate(BaseModel):
    name: str
    is_active: bool = True


class DealerMakerOut(BaseModel):
    id: int
    dealer_id: int
    maker_id: int
    dealer_name: str
    maker_name: str
    is_active: bool


class DealerMakerCreate(BaseModel):
    dealer_id: int
    maker_id: int


# ---------------------------------------------------------------------------
# ダッシュボード
# ---------------------------------------------------------------------------

class CategorySummaryOut(BaseModel):
    category_id: int
    category_name: str
    section: int
    total_sku: int
    yellow_count: int
    red_count: int


class DashboardSectionBlockOut(BaseModel):
    """ダッシュボード TOP — 棚ごとのカテゴリカード"""
    section_id: int
    section_name: str
    color: str
    sort_order: int
    categories: list[CategorySummaryOut]


class DashboardSectionsOut(BaseModel):
    """ダッシュボード TOP 用（棚一覧）"""
    sections: list[DashboardSectionBlockOut]


# ---------------------------------------------------------------------------
# 発注・納品
# ---------------------------------------------------------------------------

class PurchaseOrderItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    barcode: str
    quantity: int
    unit_price: Optional[int] = None


class PurchaseOrderOut(BaseModel):
    id: int
    store_id: int
    store_name: str
    dealer_id: int
    dealer_name: str
    order_date: date
    note: Optional[str] = None
    created_at: datetime
    item_count: int
    total_amount: Optional[int] = None
    items: list[PurchaseOrderItemOut] = []


class PurchaseOrderListItem(BaseModel):
    id: int
    store_id: int
    store_name: str
    dealer_id: int
    dealer_name: str
    order_date: date
    item_count: int
    total_amount: Optional[int] = None


class InvoiceLineDraft(BaseModel):
    product_code: str
    quantity: int
    matched_product_id: Optional[int] = None
    matched_product_name: Optional[str] = None
    match_status: str  # matched | unmatched


class InvoiceParseResult(BaseModel):
    order_date: Optional[date] = None
    dealer_name: Optional[str] = None
    lines: list[InvoiceLineDraft] = []
    raw_note: Optional[str] = None
    unmatched_count: int = 0
    notice: Optional[str] = None


class InvoiceMatchRequest(BaseModel):
    """納品書明細の再照合（ディーラー選択後）"""
    dealer_id: int
    lines: list[dict]  # {product_code, quantity}


class PurchaseOrderConfirmRequest(BaseModel):
    store_id: int
    dealer_id: int
    order_date: date
    note: Optional[str] = None
    lines: list[dict]  # {product_id, quantity, unit_price?}


# ---------------------------------------------------------------------------
# 発注データ分析
# ---------------------------------------------------------------------------


class OrderSummaryOut(BaseModel):
    total_amount: int
    total_quantity: int
    order_count: int
    sku_count: int
    has_data: bool


class OrderStoreRowOut(BaseModel):
    store_id: int
    store_name: str
    amount: int
    quantity: int
    order_count: int


class OrderSectionRowOut(BaseModel):
    section: int
    section_name: str
    amount: int
    quantity: int
    order_count: int
    ratio_percent: float


class OrderCategoryRowOut(BaseModel):
    category_id: int
    category_name: str
    section: int
    section_name: str
    amount: int
    quantity: int
    ratio_percent: float


class OrderDealerRowOut(BaseModel):
    dealer_id: int
    dealer_name: str
    amount: int
    quantity: int
    maker_count: int
    ratio_percent: float


class OrderMakerRowOut(BaseModel):
    maker_id: int
    maker_name: str
    dealer_name: str
    amount: int
    quantity: int
    ratio_percent: float


class OrderHistoryRowOut(BaseModel):
    order_id: int
    order_date: str
    store_name: str
    dealer_name: str
    item_count: int
    total_amount: int


class OrderAnalyticsListOut(BaseModel):
    has_data: bool
    items: list
