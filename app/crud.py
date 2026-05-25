"""
データベース操作（CRUD）
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.auth import verify_password
from app.models import (
    Category,
    Inventory,
    InventoryAction,
    InventoryLog,
    Product,
    ProductDeliveryCode,
    Store,
    User,
    UserRole,
)
from app.schemas import (
    InventoryItemOut,
    InventoryLogOut,
    InventoryScanRequest,
    InventoryScanResponse,
    ProductCreate,
    ProductUpdate,
    StockLevel,
    UserOut,
)


# ---------------------------------------------------------------------------
# 在庫の色分け
# ---------------------------------------------------------------------------

def calc_stock_level(quantity: int, warning: int, critical: int) -> StockLevel:
    if quantity <= critical:
        return "red"
    if quantity <= warning:
        return "yellow"
    return "green"


# ---------------------------------------------------------------------------
# ユーザー
# ---------------------------------------------------------------------------

def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(
    db: Session,
    username: str,
    password: str,
    role: UserRole,
    store_id: int | None = None,
) -> User:
    from app.auth import hash_password

    user = User(
        username=username,
        hashed_password=hash_password(password),
        role=role,
        store_id=store_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# 店舗
# ---------------------------------------------------------------------------

def get_stores(db: Session, active_only: bool = True) -> list[Store]:
    q = db.query(Store)
    if active_only:
        q = q.filter(Store.is_active.is_(True))
    return q.order_by(Store.id).all()


def get_store(db: Session, store_id: int) -> Store | None:
    return db.query(Store).filter(Store.id == store_id).first()


def create_store(db: Session, name: str) -> Store:
    store = Store(name=name, is_active=True)
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def update_store(db: Session, store: Store, *, name: str, is_active: bool) -> Store:
    store.name = name
    store.is_active = is_active
    db.commit()
    db.refresh(store)
    return store


# ---------------------------------------------------------------------------
# 商品
# ---------------------------------------------------------------------------

def get_products(db: Session, category_id: int | None = None) -> list[Product]:
    q = db.query(Product).options(
        joinedload(Product.category),
        joinedload(Product.maker),
        joinedload(Product.dealer),
    )
    if category_id is not None:
        q = q.filter(Product.category_id == category_id)
    return q.order_by(Product.name).all()


def get_product_by_barcode(db: Session, barcode: str) -> Product | None:
    return db.query(Product).filter(Product.barcode == barcode).first()


def get_product_by_jan_code(db: Session, jan_code: str) -> Product | None:
    code = (jan_code or "").strip()
    if not code:
        return None
    return db.query(Product).filter(Product.jan_code == code).first()


def resolve_product_for_scan(db: Session, scan_code: str) -> Product | None:
    """スキャナー: JANコード優先、未登録時は従来バーコードで照合"""
    code = (scan_code or "").strip()
    if not code:
        return None
    product = get_product_by_jan_code(db, code)
    if product:
        return product
    return get_product_by_barcode(db, code)


def get_product_by_delivery_code(
    db: Session, dealer_id: int, delivery_code: str
) -> Product | None:
    code = (delivery_code or "").strip()
    if not code:
        return None
    row = (
        db.query(ProductDeliveryCode)
        .filter(
            ProductDeliveryCode.dealer_id == dealer_id,
            ProductDeliveryCode.delivery_code == code,
            ProductDeliveryCode.is_active.is_(True),
        )
        .first()
    )
    if not row:
        return None
    return get_product_by_id(db, row.product_id)


def match_product_for_invoice(
    db: Session, product_code: str, dealer_id: int | None
) -> Product | None:
    """納品書: ディーラー別納品コードで照合"""
    code = (product_code or "").strip()
    if not code:
        return None
    if dealer_id:
        return get_product_by_delivery_code(db, dealer_id, code)
    rows = (
        db.query(ProductDeliveryCode)
        .filter(
            ProductDeliveryCode.delivery_code == code,
            ProductDeliveryCode.is_active.is_(True),
        )
        .all()
    )
    if len(rows) == 1:
        return get_product_by_id(db, rows[0].product_id)
    return None


def get_product_by_id(db: Session, product_id: int) -> Product | None:
    return (
        db.query(Product)
        .options(
            joinedload(Product.category),
            joinedload(Product.maker),
            joinedload(Product.dealer),
            joinedload(Product.delivery_codes).joinedload(ProductDeliveryCode.dealer),
        )
        .filter(Product.id == product_id)
        .first()
    )


def create_product(db: Session, data: ProductCreate) -> Product:
    dump = data.model_dump()
    jan = dump.get("jan_code")
    dump["jan_code"] = (jan or "").strip() or None
    product = Product(**dump)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def update_product(db: Session, product: Product, data: ProductUpdate) -> Product:
    product.name = data.name
    product.barcode = data.barcode
    product.jan_code = (data.jan_code or "").strip() or None
    product.unit = data.unit
    product.warning_threshold = data.warning_threshold
    product.critical_threshold = data.critical_threshold
    product.category_id = data.category_id
    product.maker_id = data.maker_id
    product.dealer_id = data.dealer_id
    db.commit()
    db.refresh(product)
    return product


def list_product_delivery_codes(db: Session, product_id: int) -> list[ProductDeliveryCode]:
    return (
        db.query(ProductDeliveryCode)
        .options(joinedload(ProductDeliveryCode.dealer))
        .filter(
            ProductDeliveryCode.product_id == product_id,
            ProductDeliveryCode.is_active.is_(True),
        )
        .order_by(ProductDeliveryCode.dealer_id, ProductDeliveryCode.id)
        .all()
    )


def create_product_delivery_code(
    db: Session,
    product_id: int,
    dealer_id: int,
    delivery_code: str,
    note: str | None = None,
) -> ProductDeliveryCode:
    code = delivery_code.strip()
    if not code:
        raise ValueError("納品コードを入力してください。")
    existing = (
        db.query(ProductDeliveryCode)
        .filter(
            ProductDeliveryCode.dealer_id == dealer_id,
            ProductDeliveryCode.delivery_code == code,
            ProductDeliveryCode.is_active.is_(True),
        )
        .first()
    )
    if existing and existing.product_id != product_id:
        raise ValueError("この納品コードは別の商品で使用されています。")
    if existing and existing.product_id == product_id:
        existing.note = note
        db.commit()
        db.refresh(existing)
        return existing
    row = ProductDeliveryCode(
        product_id=product_id,
        dealer_id=dealer_id,
        delivery_code=code,
        note=note,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def deactivate_product_delivery_code(db: Session, row: ProductDeliveryCode) -> None:
    row.is_active = False
    db.commit()


def get_product_delivery_code(db: Session, code_id: int) -> ProductDeliveryCode | None:
    return (
        db.query(ProductDeliveryCode)
        .options(joinedload(ProductDeliveryCode.dealer))
        .filter(ProductDeliveryCode.id == code_id)
        .first()
    )


def delete_product(db: Session, product: Product) -> None:
    """商品と関連する在庫・ログ・発注明細を削除"""
    from app.models import PurchaseOrderItem

    db.query(ProductDeliveryCode).filter(ProductDeliveryCode.product_id == product.id).delete()
    db.query(PurchaseOrderItem).filter(PurchaseOrderItem.product_id == product.id).delete()
    db.query(InventoryLog).filter(InventoryLog.product_id == product.id).delete()
    db.query(Inventory).filter(Inventory.product_id == product.id).delete()
    db.delete(product)
    db.commit()


def _parse_csv_row_dict(row: dict, row_num: int) -> dict | None:
    """ヘッダー付き CSV の1行を正規化"""
    lower = {k.strip().lower(): v.strip() for k, v in row.items() if k}

    def col(*keys: str, default: str = "") -> str:
        for k in keys:
            if k in lower and lower[k]:
                return lower[k]
        return default

    name = col("name", "商品名", "名前")
    barcode = col("barcode", "バーコード")
    if not name or not barcode:
        return None
    return {
        "row_num": row_num,
        "name": name,
        "barcode": barcode,
        "unit": col("unit", "単位") or "本",
        "warning": col("warning_threshold", "warning"),
        "critical": col("critical_threshold", "critical"),
        "category_id": col("category_id", "category"),
        "jan_code": col("jan_code", "jan"),
        "delivery_pairs": [
            (col(f"dealer_id_{i}", f"dealer_{i}"), col(f"delivery_code_{i}", f"delivery_{i}"))
            for i in range(1, 6)
        ],
    }


def import_products_csv(db: Session, csv_text: str) -> dict:
    """
    CSV から商品を一括登録・更新

    列（ヘッダー推奨）:
    name, barcode, unit, warning_threshold, critical_threshold, category_id,
    jan_code, delivery_code_1〜5, dealer_id_1〜5
    """
    import csv
    import io

    from app.schemas import ProductCreate, ProductImportResult, ProductUpdate

    result = ProductImportResult()
    stream = io.StringIO(csv_text)
    sample = stream.read(2048)
    stream.seek(0)
    has_header = "name" in sample.lower() or "商品名" in sample

    rows_to_process: list[tuple[int, dict | list[str]]] = []
    if has_header:
        reader = csv.DictReader(stream)
        for row_num, row in enumerate(reader, start=2):
            if not row or all(not (v or "").strip() for v in row.values()):
                continue
            parsed = _parse_csv_row_dict(row, row_num)
            if parsed is None:
                result.errors.append(f"{row_num}行目: 商品名とバーコードは必須です")
                result.skipped += 1
                continue
            rows_to_process.append((row_num, parsed))
    else:
        reader = csv.reader(stream)
        for row_num, row in enumerate(reader, start=1):
            if not row or all(not cell.strip() for cell in row):
                continue
            cells = [c.strip() for c in row]
            if row_num == 1 and cells[0].lower() in ("name", "商品名", "名前"):
                continue
            rows_to_process.append((row_num, cells))

    for row_num, data in rows_to_process:
        if isinstance(data, dict):
            name = data["name"]
            barcode = data["barcode"]
            unit = data["unit"]
            try:
                warning = int(data["warning"]) if data["warning"] else 5
                critical = int(data["critical"]) if data["critical"] else 2
            except ValueError:
                result.errors.append(f"{row_num}行目: 閾値は数値で入力してください")
                result.skipped += 1
                continue
            cat_id_raw = data["category_id"]
            jan_code = data["jan_code"] or None
            delivery_pairs = data["delivery_pairs"]
        else:
            cells = data
            if len(cells) < 2:
                result.errors.append(f"{row_num}行目: 列が不足しています（name, barcode 必須）")
                result.skipped += 1
                continue
            name, barcode = cells[0], cells[1]
            unit = cells[2] if len(cells) > 2 and cells[2] else "本"
            try:
                warning = int(cells[3]) if len(cells) > 3 and cells[3] else 5
                critical = int(cells[4]) if len(cells) > 4 and cells[4] else 2
            except ValueError:
                result.errors.append(f"{row_num}行目: 閾値は数値で入力してください")
                result.skipped += 1
                continue
            cat_id_raw = cells[5] if len(cells) > 5 else ""
            jan_code = cells[6].strip() if len(cells) > 6 and cells[6] else None
            delivery_pairs = []
            base = 7
            for i in range(5):
                d_idx = base + i * 2
                c_idx = d_idx + 1
                dealer_v = cells[d_idx] if len(cells) > d_idx else ""
                code_v = cells[c_idx] if len(cells) > c_idx else ""
                delivery_pairs.append((dealer_v, code_v))

        existing = get_product_by_barcode(db, barcode)
        try:
            if existing:
                cat_id = int(cat_id_raw) if cat_id_raw else existing.category_id
                update_product(
                    db,
                    existing,
                    ProductUpdate(
                        name=name,
                        barcode=barcode,
                        jan_code=jan_code,
                        unit=unit,
                        warning_threshold=warning,
                        critical_threshold=critical,
                        category_id=cat_id,
                        maker_id=existing.maker_id,
                        dealer_id=existing.dealer_id,
                    ),
                )
                product = existing
                result.updated += 1
            else:
                cat_id = int(cat_id_raw) if cat_id_raw else 1
                product = create_product(
                    db,
                    ProductCreate(
                        name=name,
                        barcode=barcode,
                        jan_code=jan_code,
                        unit=unit,
                        warning_threshold=warning,
                        critical_threshold=critical,
                        category_id=cat_id,
                    ),
                )
                result.created += 1

            for dealer_v, code_v in delivery_pairs:
                if not dealer_v or not code_v:
                    continue
                try:
                    create_product_delivery_code(
                        db,
                        product.id,
                        int(dealer_v),
                        code_v,
                    )
                except Exception as ex:
                    result.errors.append(f"{row_num}行目 納品コード: {ex}")

        except Exception as e:
            result.errors.append(f"{row_num}行目: {e}")
            result.skipped += 1
            db.rollback()

    return result.model_dump()


# ---------------------------------------------------------------------------
# 在庫
# ---------------------------------------------------------------------------

def get_or_create_inventory(db: Session, store_id: int, product_id: int) -> Inventory:
    """店舗×商品の在庫レコードを取得（なければ0で作成）"""
    inv = (
        db.query(Inventory)
        .filter(Inventory.store_id == store_id, Inventory.product_id == product_id)
        .first()
    )
    if inv:
        return inv
    inv = Inventory(store_id=store_id, product_id=product_id, quantity=0)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def get_inventory_list(
    db: Session, store_id: int, category_id: int | None = None
) -> list[InventoryItemOut]:
    """店舗の在庫一覧（未登録は quantity=0）。category_id で絞り込み可"""
    products = get_products(db, category_id=category_id)
    result: list[InventoryItemOut] = []

    for product in products:
        inv = (
            db.query(Inventory)
            .filter(
                Inventory.store_id == store_id,
                Inventory.product_id == product.id,
            )
            .first()
        )
        quantity = inv.quantity if inv else 0
        level = calc_stock_level(
            quantity, product.warning_threshold, product.critical_threshold
        )
        result.append(
            InventoryItemOut(
                product_id=product.id,
                product_name=product.name,
                barcode=product.barcode,
                unit=product.unit,
                quantity=quantity,
                stock_level=level,
                warning_threshold=product.warning_threshold,
                critical_threshold=product.critical_threshold,
                category_id=product.category_id,
            )
        )
    return result


def scan_inventory(
    db: Session,
    user: User,
    data: InventoryScanRequest,
) -> InventoryScanResponse:
    """スキャンコード（JAN優先）で在庫を増減し、ログを残す"""
    product = resolve_product_for_scan(db, data.barcode)
    if not product:
        raise ValueError(f"コード {data.barcode} の商品が見つかりません（JANコードを確認してください）。")

    inv = get_or_create_inventory(db, data.store_id, product.id)

    if data.action == InventoryAction.USE:
        if inv.quantity < data.quantity:
            raise ValueError(
                f"在庫が足りません（現在: {inv.quantity}{product.unit}）"
            )
        inv.quantity -= data.quantity
        action_label = "使用"
    else:
        inv.quantity += data.quantity
        action_label = "補充"

    level = calc_stock_level(
        inv.quantity, product.warning_threshold, product.critical_threshold
    )

    log = InventoryLog(
        store_id=data.store_id,
        product_id=product.id,
        user_id=user.id,
        action=data.action,
        quantity_change=data.quantity,
        quantity_after=inv.quantity,
    )
    db.add(log)
    db.commit()
    db.refresh(inv)

    return InventoryScanResponse(
        product_name=product.name,
        action=data.action,
        quantity_change=data.quantity,
        quantity_after=inv.quantity,
        stock_level=level,
        message=f"{product.name} を{action_label}しました（残り {inv.quantity}{product.unit}）",
    )


def get_recent_logs(db: Session, store_id: int, days: int = 14) -> list[InventoryLogOut]:
    """AI分析用：直近の在庫変動ログ"""
    since = datetime.utcnow() - timedelta(days=days)
    logs = (
        db.query(InventoryLog)
        .options(
            joinedload(InventoryLog.product),
            joinedload(InventoryLog.user),
        )
        .filter(
            InventoryLog.store_id == store_id,
            InventoryLog.created_at >= since,
        )
        .order_by(InventoryLog.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        InventoryLogOut(
            id=log.id,
            store_id=log.store_id,
            product_id=log.product_id,
            product_name=log.product.name,
            action=log.action,
            quantity_change=log.quantity_change,
            quantity_after=log.quantity_after,
            username=log.user.username,
            created_at=log.created_at,
        )
        for log in logs
    ]


def build_analysis_context(
    db: Session, store_id: int, category_id: int | None = None
) -> dict:
    """Claude に渡す在庫サマリー"""
    store = get_store(db, store_id)
    items = get_inventory_list(db, store_id, category_id=category_id)
    logs = get_recent_logs(db, store_id, days=7)
    category_name = ""
    if category_id:
        cat = db.query(Category).filter(Category.id == category_id).first()
        category_name = cat.name if cat else ""

    return {
        "store_name": store.name if store else "",
        "category_name": category_name,
        "inventory": [
            {
                "name": i.product_name,
                "quantity": i.quantity,
                "unit": i.unit,
                "level": i.stock_level,
            }
            for i in items
        ],
        "recent_logs": [
            {
                "product": l.product_name,
                "action": l.action.value,
                "change": l.quantity_change,
                "after": l.quantity_after,
                "at": l.created_at.isoformat(),
            }
            for l in logs[:30]
        ],
    }
