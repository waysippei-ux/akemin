"""
棚補充・使用 — 画面ルート・API
"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, crud_masters, crud_stock
from app.auth import (
    check_store_access,
    get_current_user,
    get_optional_user,
    is_admin,
    require_admin,
)
from app.config import BASE_DIR
from app.database import get_db
from app.models import InventoryAction, User, UserRole
from app.schemas import (
    BrandOut,
    CategoryOut,
    DealerOut,
    InventoryItemOut,
    InventoryScanResponse,
    MakerOut,
    SectionOut,
    StockBulkParseResult,
    StockBulkRegisterRequest,
    StockConsumeRequest,
    StockLookupOut,
    StockLogEditIn,
    StockLogRowOut,
    StockLogsTodayOut,
    StockQuantityOut,
    StockRegisterWithProductRequest,
    StockReplenishRequest,
    StoreOut,
    StoreProductSettingProductOut,
    StoreProductSettingProductPut,
)
from app.services.invoice_parser import parse_invoice_file

templates = Jinja2Templates(directory=str((BASE_DIR / "templates").resolve()))

pages_router = APIRouter(tags=["棚補充・使用 画面"])
router = APIRouter()

ALLOWED_UPLOAD_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


def _stores_for_user(db: Session, current_user: User) -> list[StoreOut]:
    if current_user.role == UserRole.STAFF and current_user.store_id:
        store = crud.get_store(db, current_user.store_id)
        rows = [store] if store and store.is_active else []
    else:
        rows = crud.get_all_stores(db, active_only=True)
    return [StoreOut.model_validate(s) for s in rows]


def _masters(
    db: Session,
    current_user: User,
) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict], list[dict]]:
    stores = [s.model_dump(mode="json") for s in _stores_for_user(db, current_user)]
    sections = [
        SectionOut.model_validate(s).model_dump(mode="json")
        for s in crud_masters.get_sections(db, active_only=True)
    ]
    categories = [
        CategoryOut.model_validate(c).model_dump(mode="json")
        for c in crud_masters.get_categories(db, active_only=True)
    ]
    makers = [
        MakerOut.model_validate(m).model_dump(mode="json")
        for m in crud_masters.get_makers(db, active_only=True)
    ]
    dealers = [
        DealerOut.model_validate(d).model_dump(mode="json")
        for d in crud_masters.get_dealers(db, active_only=True)
    ]
    brands = [
        BrandOut.model_validate(b).model_dump(mode="json")
        for b in crud_masters.get_brands(db, active_maker_only=True)
    ]
    return stores, sections, categories, makers, dealers, brands


def _resolve_default_store_id(
    stores: list[dict], store_id: Optional[int]
) -> Optional[int]:
    store_ids = {s["id"] for s in stores}
    if store_id and store_id in store_ids:
        return store_id
    return stores[0]["id"] if stores else None


def _products_for_store(
    db: Session, store_id: int, *, active_only: bool
) -> list[dict[str, Any]]:
    return [
        InventoryItemOut.model_validate(item).model_dump(mode="json")
        for item in crud.get_inventory_list(db, store_id, active_only=active_only)
    ]


def _page_context_anonymous(
    db: Session,
    page: Literal["replenish", "consume"],
    store_id: Optional[int] = None,
) -> dict[str, Any]:
    """ブラウザ直アクセス時（JWT 未送信）— クライアント側で /api/auth/me 後に店舗を絞る"""
    stores = [
        StoreOut.model_validate(s).model_dump(mode="json")
        for s in crud.get_all_stores(db, active_only=True)
    ]
    sections = [
        SectionOut.model_validate(s).model_dump(mode="json")
        for s in crud_masters.get_sections(db, active_only=True)
    ]
    categories = [
        CategoryOut.model_validate(c).model_dump(mode="json")
        for c in crud_masters.get_categories(db, active_only=True)
    ]
    makers = [
        MakerOut.model_validate(m).model_dump(mode="json")
        for m in crud_masters.get_makers(db, active_only=True)
    ]
    dealers = [
        DealerOut.model_validate(d).model_dump(mode="json")
        for d in crud_masters.get_dealers(db, active_only=True)
    ]
    brands = [
        BrandOut.model_validate(b).model_dump(mode="json")
        for b in crud_masters.get_brands(db, active_maker_only=True)
    ]
    default_store_id = _resolve_default_store_id(stores, store_id)
    active_only = page == "consume"
    products: list[dict[str, Any]] = []
    if default_store_id is not None:
        products = _products_for_store(db, default_store_id, active_only=active_only)
    page_json = {
        "page": page,
        "stores": stores,
        "sections": sections,
        "categories": categories,
        "makers": makers,
        "dealers": dealers,
        "brands": brands,
        "products": products,
        "default_store_id": default_store_id,
    }
    return {
        "stores": stores,
        "sections": sections,
        "categories": categories,
        "makers": makers,
        "dealers": dealers,
        "brands": brands,
        "products": products,
        "default_store_id": default_store_id,
        "user_role": "",
        "page_json": json.dumps(page_json, ensure_ascii=False),
    }


def _page_context(
    db: Session,
    page: Literal["replenish", "consume"],
    current_user: User,
    store_id: Optional[int] = None,
) -> dict[str, Any]:
    stores, sections, categories, makers, dealers, brands = _masters(db, current_user)
    default_store_id = _resolve_default_store_id(stores, store_id)
    if current_user.role == UserRole.STAFF and current_user.store_id:
        default_store_id = current_user.store_id
    active_only = page == "consume"
    products: list[dict[str, Any]] = []
    if default_store_id is not None:
        products = _products_for_store(db, default_store_id, active_only=active_only)

    page_json = {
        "page": page,
        "stores": stores,
        "sections": sections,
        "categories": categories,
        "makers": makers,
        "dealers": dealers,
        "brands": brands,
        "products": products,
        "default_store_id": default_store_id,
    }
    return {
        "stores": stores,
        "sections": sections,
        "categories": categories,
        "makers": makers,
        "dealers": dealers,
        "brands": brands,
        "products": products,
        "default_store_id": default_store_id,
        "user_role": current_user.role.value,
        "page_json": json.dumps(page_json, ensure_ascii=False),
    }


@pages_router.get("/stock/replenish")
def stock_replenish_page(
    request: Request,
    db: Session = Depends(get_db),
    store_id: Optional[int] = Query(None, gt=0),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """HTML 画面 — 認証はクライアント（localStorage）+ API。Cookie があれば SSR で店舗を絞る"""
    ctx = (
        _page_context(db, "replenish", current_user, store_id)
        if current_user
        else _page_context_anonymous(db, "replenish", store_id)
    )
    return templates.TemplateResponse(request, "stock_replenish.html", ctx)


@pages_router.get("/stock/consume")
def stock_consume_page(
    request: Request,
    db: Session = Depends(get_db),
    store_id: Optional[int] = Query(None, gt=0),
    current_user: Optional[User] = Depends(get_optional_user),
):
    ctx = (
        _page_context(db, "consume", current_user, store_id)
        if current_user
        else _page_context_anonymous(db, "consume", store_id)
    )
    return templates.TemplateResponse(request, "stock_consume.html", ctx)


def _validate_store(db: Session, store_id: int) -> None:
    crud.require_store_id_for_stock(store_id)
    if not crud.get_store(db, store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")


@router.get("/products", response_model=list[InventoryItemOut])
def list_stock_products(
    store_id: int = Query(..., gt=0),
    page: Literal["replenish", "consume"] = Query(...),
    category_id: Optional[int] = Query(None, gt=0),
    section: Optional[int] = Query(None, gt=0),
    maker_id: Optional[int] = Query(None, gt=0),
    brand_id: Optional[int] = Query(None, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """店舗切り替え時の商品一覧（category_name / brand_name / maker_name / standard_stock 含む）"""
    check_store_access(current_user, store_id)
    _validate_store(db, store_id)
    active_only = page == "consume"
    return crud.get_inventory_list(
        db,
        store_id,
        category_id=category_id,
        maker_id=maker_id,
        brand_id=brand_id,
        section=section,
        active_only=active_only,
    )


@router.get("/quantity", response_model=StockQuantityOut)
def get_stock_quantity(
    store_id: int = Query(..., gt=0),
    product_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """店舗×商品の現在庫（モーダル用）"""
    check_store_access(current_user, store_id)
    _validate_store(db, store_id)
    try:
        qty, unit, on_shelf = crud_stock.get_product_quantity_at_store(
            db, store_id, product_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return StockQuantityOut(
        store_id=store_id,
        product_id=product_id,
        quantity=qty,
        unit=unit,
        is_on_shelf=on_shelf,
    )


@router.post("/replenish", response_model=InventoryScanResponse)
def replenish_stock(
    body: StockReplenishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """棚補充（在庫+・is_active=true）"""
    check_store_access(current_user, body.store_id)
    _validate_store(db, body.store_id)
    try:
        return crud_stock.replenish_stock(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/consume", response_model=InventoryScanResponse)
def consume_stock(
    body: StockConsumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """使用済み（在庫-・0未満不可）"""
    check_store_access(current_user, body.store_id)
    _validate_store(db, body.store_id)
    try:
        return crud_stock.consume_stock(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/lookup", response_model=StockLookupOut)
def lookup_product(
    store_id: int = Query(..., gt=0),
    code: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """バーコードで商品照合"""
    check_store_access(current_user, store_id)
    _validate_store(db, store_id)
    return crud_stock.lookup_stock_product(db, store_id, code)


@router.get("/logs", response_model=list[StockLogRowOut])
def list_stock_logs_endpoint(
    store_id: int = Query(..., gt=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """補充・使用の登録履歴（直近N件）"""
    check_store_access(current_user, store_id)
    _validate_store(db, store_id)
    return crud.list_stock_logs(db, store_id=store_id, limit=limit)


@router.get("/logs/today", response_model=StockLogsTodayOut)
def list_stock_logs_today_endpoint(
    store_id: int = Query(..., gt=0),
    type: Literal["replenish", "consume"] = Query(..., description="replenish | consume"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当日（JST）の補充/使用履歴（全件＋件数）— crud で JST→UTC 日付範囲フィルタ"""
    check_store_access(current_user, store_id)
    _validate_store(db, store_id)
    if type not in ("replenish", "consume"):
        raise HTTPException(status_code=400, detail="type は replenish または consume を指定してください。")
    try:
        data = crud.list_stock_logs_today(db, store_id=store_id, log_type=type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StockLogsTodayOut(**data)


@router.put("/logs/{log_id}", response_model=StockLogRowOut)
def edit_stock_log_endpoint(
    log_id: int,
    body: StockLogEditIn,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    """登録履歴の数量を修正（管理者のみ）"""
    try:
        log = crud.edit_stock_log(
            db,
            log_id=log_id,
            new_quantity=body.quantity,
            reason=body.reason,
            editor_user=admin_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    store = crud.get_store(db, log.store_id)
    store_name = store.name if store else ""
    product = crud.get_product_by_id(db, log.product_id)
    return StockLogRowOut(
        id=log.id,
        store_id=log.store_id,
        store_name=store_name,
        product_id=log.product_id,
        product_name=product.name if product else "",
        unit=(product.unit if product else "本") or "本",
        action=log.action,
        quantity_change=log.quantity_change,
        quantity_after=log.quantity_after,
        created_at=log.created_at,
        recorded_at=crud.format_log_recorded_at_jst(log.created_at),
        is_edited=bool(getattr(log, "is_edited", False)),
    )


@router.post("/register-with-product", response_model=InventoryScanResponse)
def register_with_new_product(
    body: StockRegisterWithProductRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """未登録商品を新規登録してから棚に反映（補充用）"""
    check_store_access(current_user, body.store_id)
    _validate_store(db, body.store_id)
    try:
        return crud_stock.register_stock_with_new_product(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/bulk-register")
def bulk_register(
    body: StockBulkRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """複数商品をまとめて在庫反映"""
    check_store_access(current_user, body.store_id)
    _validate_store(db, body.store_id)
    try:
        return crud_stock.bulk_register_stock(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/bulk-parse", response_model=StockBulkParseResult)
async def bulk_parse(
    file: UploadFile = File(...),
    store_id: int = Query(..., gt=0),
    dealer_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """写真・PDFから明細を読み取りマスタと照合"""
    check_store_access(current_user, store_id)
    _validate_store(db, store_id)

    media = file.content_type or "image/jpeg"
    if media not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(400, "JPEG / PNG / WebP / PDF のみ対応しています。")

    raw = await file.read()
    try:
        parsed = parse_invoice_file(raw, media)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return crud_stock.build_stock_bulk_parse_result(db, store_id, parsed, dealer_id)


@router.get("/store-settings/product", response_model=StoreProductSettingProductOut)
def get_stock_product_setting(
    store_id: int = Query(..., gt=0),
    product_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """店舗×商品の発注目安を取得（ログイン済み・スタッフは自店舗のみ）"""
    check_store_access(current_user, store_id)
    if not crud.get_store(db, store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")
    try:
        return crud.get_store_product_setting(db, store_id, product_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/store-settings/product", response_model=StoreProductSettingProductOut)
def put_stock_product_setting(
    body: StoreProductSettingProductPut,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """店舗×商品の発注目安を UPSERT（管理者のみ）"""
    if not is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="発注目安の編集は管理者権限が必要です",
        )
    check_store_access(current_user, body.store_id)
    if not crud.get_store(db, body.store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")

    product = crud.get_product_by_id(db, body.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品が見つかりません。")

    warning = (
        body.warning_threshold
        if body.warning_threshold is not None
        else product.warning_threshold
    )
    critical = (
        body.critical_threshold
        if body.critical_threshold is not None
        else product.critical_threshold
    )

    try:
        crud.upsert_store_product_setting_product(
            db,
            body.store_id,
            body.product_id,
            standard_stock=body.standard_stock,
            warning_threshold=warning,
            critical_threshold=critical,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return crud.get_store_product_setting(db, body.store_id, body.product_id)
