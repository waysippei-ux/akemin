"""発注・納品管理 API"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, crud_masters
from app.config import BASE_DIR
from app.auth import check_store_access, get_current_user, require_admin
from app.models import JST
from app.crud_inventory_analytics import get_inventory_analytics
from app.crud_order_analytics import (
    TAB_LABELS,
    OrderFilter,
    build_csv_string,
    build_tab_csv_rows,
    get_by_category,
    get_by_dealer,
    get_by_brand,
    get_by_maker,
    get_by_section,
    get_by_store,
    get_history,
    get_summary,
    has_order_data,
    iter_detail_csv_rows,
)
from app.database import get_db
from app.models import User
from app.schemas import (
    InvoiceLineDraft,
    InvoiceMatchRequest,
    InvoiceParseResult,
    InventoryAnalyticsOut,
    OrderAnalyticsListOut,
    OrderSummaryOut,
    PurchaseOrderConfirmRequest,
    PurchaseOrderListItem,
    PurchaseOrderOut,
)
from app.services.invoice_parser import parse_invoice_file

router = APIRouter()
templates = Jinja2Templates(directory=str((BASE_DIR / "templates").resolve()))

ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}

EXPORT_TABS = frozenset({"store", "section", "category", "dealer", "maker", "brand", "history"})


def _build_filter(
    year: Optional[int] = None,
    month: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    store_id: Optional[int] = None,
    section: Optional[int] = None,
    category_id: Optional[int] = None,
    dealer_id: Optional[int] = None,
    maker_id: Optional[int] = None,
    brand_id: Optional[int] = None,
) -> OrderFilter:
    now = datetime.now(JST)
    use_month = not date_from and not date_to
    if use_month:
        if year is None:
            year = now.year
        if month is None:
            month = now.month
    else:
        year = None
        month = None
    return OrderFilter(
        year=year,
        month=month,
        date_from=date_from,
        date_to=date_to,
        store_id=store_id,
        section=section,
        category_id=category_id,
        dealer_id=dealer_id,
        maker_id=maker_id,
        brand_id=brand_id,
    )


def _apply_user_scope(f: OrderFilter, user: User) -> OrderFilter:
    if user.role.value == "staff":
        if f.store_id and f.store_id != user.store_id:
            raise HTTPException(403, "この店舗のデータにはアクセスできません。")
        f.store_id = user.store_id
    elif f.store_id:
        check_store_access(user, f.store_id)
    return f


def _filter_dep(
    year: Optional[int] = None,
    month: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    store_id: Optional[int] = None,
    section: Optional[int] = None,
    category_id: Optional[int] = None,
    dealer_id: Optional[int] = None,
    maker_id: Optional[int] = None,
    brand_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> OrderFilter:
    f = _build_filter(
        year=year,
        month=month,
        date_from=date_from,
        date_to=date_to,
        store_id=store_id,
        section=section,
        category_id=category_id,
        dealer_id=dealer_id,
        maker_id=maker_id,
        brand_id=brand_id,
    )
    return _apply_user_scope(f, current_user)


def _csv_response(rows: list[list], filename: str) -> Response:
    encoded = quote(filename)
    return Response(
        content=build_csv_string(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        },
    )


def _period_suffix(f: OrderFilter) -> str:
    if f.date_from and f.date_to:
        return f"{f.date_from.isoformat()}_{f.date_to.isoformat()}"
    if f.year and f.month:
        return f"{f.year:04d}-{f.month:02d}"
    if f.year:
        return f"{f.year:04d}"
    return "all"


# ---------------------------------------------------------------------------
# 発注データ分析（/{order_id} より前に定義）
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=OrderSummaryOut)
def order_summary(f: OrderFilter = Depends(_filter_dep), db: Session = Depends(get_db)):
    return get_summary(db, f)


@router.get("/by-store", response_model=OrderAnalyticsListOut)
def orders_by_store(f: OrderFilter = Depends(_filter_dep), db: Session = Depends(get_db)):
    items = get_by_store(db, f)
    return OrderAnalyticsListOut(has_data=has_order_data(db, f), items=items)


@router.get("/by-section", response_model=OrderAnalyticsListOut)
def orders_by_section(f: OrderFilter = Depends(_filter_dep), db: Session = Depends(get_db)):
    items = get_by_section(db, f)
    return OrderAnalyticsListOut(has_data=has_order_data(db, f), items=items)


@router.get("/by-category", response_model=OrderAnalyticsListOut)
def orders_by_category(f: OrderFilter = Depends(_filter_dep), db: Session = Depends(get_db)):
    items = get_by_category(db, f)
    return OrderAnalyticsListOut(has_data=has_order_data(db, f), items=items)


@router.get("/by-dealer", response_model=OrderAnalyticsListOut)
def orders_by_dealer(f: OrderFilter = Depends(_filter_dep), db: Session = Depends(get_db)):
    items = get_by_dealer(db, f)
    return OrderAnalyticsListOut(has_data=has_order_data(db, f), items=items)


@router.get("/by-maker", response_model=OrderAnalyticsListOut)
def orders_by_maker(f: OrderFilter = Depends(_filter_dep), db: Session = Depends(get_db)):
    items = get_by_maker(db, f)
    return OrderAnalyticsListOut(has_data=has_order_data(db, f), items=items)


@router.get("/by-brand", response_model=OrderAnalyticsListOut)
def orders_by_brand(f: OrderFilter = Depends(_filter_dep), db: Session = Depends(get_db)):
    items = get_by_brand(db, f)
    return OrderAnalyticsListOut(has_data=has_order_data(db, f), items=items)


@router.get("/history", response_model=OrderAnalyticsListOut)
def orders_history(f: OrderFilter = Depends(_filter_dep), db: Session = Depends(get_db)):
    items = get_history(db, f)
    return OrderAnalyticsListOut(has_data=has_order_data(db, f), items=items)


@router.get("/inventory-insights", response_model=InventoryAnalyticsOut)
def inventory_insights(
    f: OrderFilter = Depends(_filter_dep),
    db: Session = Depends(get_db),
):
    """棚の動き: 人気商品・動きのない商品・店舗別品揃え"""
    return get_inventory_analytics(db, f)


@router.get("/export/csv")
def export_orders_csv(
    tab: str = Query(..., description="store|section|category|dealer|maker|brand|history"),
    f: OrderFilter = Depends(_filter_dep),
    db: Session = Depends(get_db),
):
    if tab not in EXPORT_TABS:
        raise HTTPException(
            400,
            "tab は store / section / category / dealer / maker / brand / history のいずれかです。",
        )
    rows = build_tab_csv_rows(db, tab, f)
    label = TAB_LABELS.get(tab, tab)
    filename = f"AKEMIN_発注データ_{label}_{_period_suffix(f)}.csv"
    return _csv_response(rows, filename)


@router.get("/export/all-csv")
def export_all_orders_csv(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = iter_detail_csv_rows(db, None)
    filename = "AKEMIN_発注データ_全明細.csv"
    return _csv_response(rows, filename)


# ---------------------------------------------------------------------------
# 既存 API（互換維持）
# ---------------------------------------------------------------------------


@router.get("", response_model=list[PurchaseOrderListItem])
def list_orders(
    store_id: Optional[int] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return crud_masters.list_purchase_orders(db, store_id=store_id, year=year, month=month)


@router.get("/stats/dealers")
def dealer_stats(
    year: int = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return crud_masters.dealer_monthly_totals(db, year)


@router.get("/stats/makers")
def maker_stats(
    year: int = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return crud_masters.maker_monthly_quantities(db, year)


@router.get("/{order_id}", response_model=PurchaseOrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    po = crud_masters.get_purchase_order(db, order_id)
    if not po:
        raise HTTPException(404, "発注が見つかりません。")
    return po


def _invoice_lines_from_rows(
    db: Session,
    rows: list[dict],
    dealer_id: Optional[int] = None,
) -> tuple[list[InvoiceLineDraft], int]:
    lines: list[InvoiceLineDraft] = []
    unmatched = 0
    for row in rows:
        code = row.get("product_code", "")
        qty = int(row.get("quantity", 1))
        product = crud.match_product_for_invoice(db, code, dealer_id)
        if not product:
            unmatched += 1
        lines.append(
            InvoiceLineDraft(
                product_code=code,
                quantity=qty,
                matched_product_id=product.id if product else None,
                matched_product_name=product.name if product else None,
                match_status="matched" if product else "unmatched",
            )
        )
    return lines, unmatched


def _invoice_parse_result(
    db: Session,
    parsed: dict,
    dealer_id: Optional[int] = None,
) -> InvoiceParseResult:
    lines, unmatched = _invoice_lines_from_rows(db, parsed.get("lines", []), dealer_id)
    notice = None
    if unmatched:
        notice = (
            f"未照合の明細が {unmatched} 件あります。"
            "商品マスタで納品コード（ディーラー別）を登録するか、管理者にご確認ください。"
        )
    return InvoiceParseResult(
        order_date=parsed.get("order_date"),
        dealer_name=parsed.get("dealer_name"),
        lines=lines,
        raw_note=parsed.get("raw_note"),
        unmatched_count=unmatched,
        notice=notice,
    )


@router.post("/match-invoice-lines", response_model=InvoiceParseResult)
def match_invoice_lines(
    body: InvoiceMatchRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """ディーラー選択後に納品コードで明細を再照合"""
    lines, unmatched = _invoice_lines_from_rows(db, body.lines, body.dealer_id)
    notice = None
    if unmatched:
        notice = (
            f"未照合の明細が {unmatched} 件あります。"
            "商品マスタで納品コード（ディーラー別）を登録するか、管理者にご確認ください。"
        )
    return InvoiceParseResult(
        lines=lines,
        unmatched_count=unmatched,
        notice=notice,
    )


@router.post("/parse-invoice", response_model=InvoiceParseResult)
async def parse_invoice(
    file: UploadFile = File(...),
    dealer_id: Optional[int] = Query(None, description="照合に使うディーラーID"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    media = file.content_type or "image/jpeg"
    if media not in ALLOWED_TYPES:
        raise HTTPException(400, "JPEG / PNG / WebP / PDF のみ対応しています。")

    raw = await file.read()
    try:
        parsed = parse_invoice_file(raw, media)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return _invoice_parse_result(db, parsed, dealer_id)


@router.post("/confirm", response_model=PurchaseOrderOut)
def confirm_order(
    body: PurchaseOrderConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    dealer = crud_masters.get_dealer(db, body.dealer_id)
    if not dealer or not dealer.is_active:
        raise HTTPException(400, "ディーラーが無効です。")

    valid_lines = [ln for ln in body.lines if ln.get("product_id")]
    if not valid_lines:
        raise HTTPException(400, "反映する商品がありません。")

    return crud_masters.confirm_purchase_order(
        db,
        current_user,
        body.store_id,
        body.dealer_id,
        body.order_date,
        valid_lines,
        body.note,
    )


@router.post("/create-pdf")
def create_order_pdf(
    request: Request,
    store_id: int = Query(..., gt=0),
    shelf_id: int = Query(..., gt=0, description="棚（sections.id）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """指定棚の黄アラート以下商品で発注表 HTML を返す（ブラウザ印刷用）"""
    check_store_access(current_user, store_id)
    try:
        store_name, shelf_name, today_jst, order_data = crud.build_order_pdf_hierarchy(
            db, store_id, shelf_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return templates.TemplateResponse(
        request,
        "order_pdf.html",
        {
            "store_name": store_name,
            "shelf_name": shelf_name,
            "today": today_jst,
            "order_data": order_data,
        },
        media_type="text/html; charset=utf-8",
    )
