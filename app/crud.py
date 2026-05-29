"""
データベース操作（CRUD）
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.auth import verify_password
from app.crud_store_settings import (
    get_settings_map,
    resolve_standard_stock,
    resolve_thresholds,
)
from app.models import (
    JST,
    Brand,
    Category,
    DealerMaker,
    Inventory,
    InventoryAction,
    InventoryLog,
    InventoryLogEdit,
    Maker,
    Product,
    ProductDeliveryCode,
    Store,
    User,
    UserRole,
)
from app.schemas import (
    BrandOut,
    InventoryItemOut,
    InventoryLogOut,
    InventoryScanRequest,
    InventoryScanResponse,
    MakerOut,
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


def delete_store(db: Session, store: Store) -> None:
    """在庫・ユーザー・発注が未紐づけの店舗のみ物理削除"""
    from app.models import Inventory, PurchaseOrder, User

    if db.query(Inventory).filter(Inventory.store_id == store.id).first():
        raise ValueError("この店舗には在庫データが紐づいています")
    if db.query(User).filter(User.store_id == store.id).first():
        raise ValueError("この店舗に所属するユーザーがいます")
    if db.query(PurchaseOrder).filter(PurchaseOrder.store_id == store.id).first():
        raise ValueError("この店舗には発注データが紐づいています")
    db.delete(store)
    db.commit()


# ---------------------------------------------------------------------------
# ディーラー × メーカー（管理画面モーダル用）
# ---------------------------------------------------------------------------

def get_makers_linked_to_dealer(db: Session, dealer_id: int) -> list[MakerOut]:
    rows = (
        db.query(Maker)
        .join(DealerMaker, DealerMaker.maker_id == Maker.id)
        .filter(
            DealerMaker.dealer_id == dealer_id,
            DealerMaker.is_active.is_(True),
            Maker.is_active.is_(True),
        )
        .order_by(Maker.name)
        .all()
    )
    return [MakerOut.model_validate(m) for m in rows]


def link_maker_to_dealer(db: Session, *, dealer_id: int, maker_id: int) -> MakerOut:
    maker = db.query(Maker).filter(Maker.id == maker_id, Maker.is_active.is_(True)).first()
    if not maker:
        raise ValueError("メーカーが見つかりません。")

    existing = (
        db.query(DealerMaker)
        .filter(DealerMaker.dealer_id == dealer_id, DealerMaker.maker_id == maker_id)
        .first()
    )
    if existing:
        existing.is_active = True
        db.commit()
        return MakerOut.model_validate(maker)

    dm = DealerMaker(dealer_id=dealer_id, maker_id=maker_id, is_active=True)
    db.add(dm)
    db.commit()
    return MakerOut.model_validate(maker)


def unlink_maker_from_dealer(db: Session, *, dealer_id: int, maker_id: int) -> bool:
    dm = (
        db.query(DealerMaker)
        .filter(
            DealerMaker.dealer_id == dealer_id,
            DealerMaker.maker_id == maker_id,
            DealerMaker.is_active.is_(True),
        )
        .first()
    )
    if not dm:
        return False
    dm.is_active = False
    db.commit()
    return True


# ---------------------------------------------------------------------------
# メーカー × ブランド（管理画面モーダル用）
# ---------------------------------------------------------------------------

def get_brands_linked_to_maker(db: Session, maker_id: int) -> list[BrandOut]:
    from app import crud_masters

    if not crud_masters.get_maker(db, maker_id):
        raise ValueError("メーカーが見つかりません。")
    rows = crud_masters.get_brands(db, maker_id=maker_id, active_maker_only=False)
    return [crud_masters.brand_to_out(b) for b in rows]


def link_brand_to_maker(db: Session, *, maker_id: int, brand_id: int) -> BrandOut:
    from app import crud_masters

    if not crud_masters.get_maker(db, maker_id):
        raise ValueError("メーカーが見つかりません。")
    brand = crud_masters.get_brand(db, brand_id)
    if not brand:
        raise ValueError("ブランドが見つかりません。")
    brand.maker_id = maker_id
    db.commit()
    db.refresh(brand)
    return crud_masters.brand_to_out(brand)


def unlink_brand_from_maker(db: Session, *, maker_id: int, brand_id: int) -> bool:
    brand = (
        db.query(Brand)
        .filter(Brand.id == brand_id, Brand.maker_id == maker_id)
        .first()
    )
    if not brand:
        return False
    brand.maker_id = None
    db.commit()
    return True


# ---------------------------------------------------------------------------
# 商品
# ---------------------------------------------------------------------------

def _validate_product_brand(
    db: Session, maker_id: int | None, brand_id: int | None
) -> None:
    if brand_id is None:
        return
    from app import crud_masters

    brand = crud_masters.get_brand(db, brand_id)
    if not brand:
        raise ValueError("ブランドが見つかりません。")
    if not maker_id:
        raise ValueError("ブランドを指定する場合はメーカーを選択してください。")
    if brand.maker_id is not None and brand.maker_id != maker_id:
        raise ValueError("ブランドは選択したメーカーに属していません。")


def get_products(
    db: Session,
    category_id: int | None = None,
    *,
    maker_id: int | None = None,
    brand_id: int | None = None,
    section: int | None = None,
) -> list[Product]:
    q = db.query(Product).options(
        joinedload(Product.category).joinedload(Category.shelf_section),
        joinedload(Product.maker),
        joinedload(Product.dealer),
        joinedload(Product.brand),
    )
    if category_id is not None:
        q = q.filter(Product.category_id == category_id)
    if maker_id is not None:
        q = q.filter(Product.maker_id == maker_id)
    if brand_id is not None:
        q = q.filter(Product.brand_id == brand_id)
    if section is not None:
        q = q.join(Category).filter(Category.section == section)
    return q.order_by(Product.name).all()


AUTO_BARCODE_PREFIX = "_auto_"


def coerce_product_barcode(barcode: str | None) -> str | None:
    """空文字は未入力扱い。自動採番バーコードはそのまま返す。"""
    code = (barcode or "").strip()
    return code or None


def is_auto_barcode(barcode: str | None) -> bool:
    return bool(barcode and barcode.startswith(AUTO_BARCODE_PREFIX))


def generate_auto_barcode(db: Session) -> str:
    import uuid

    while True:
        code = f"{AUTO_BARCODE_PREFIX}{uuid.uuid4().hex[:16]}"
        if not get_product_by_barcode(db, code):
            return code


def resolve_product_barcode(
    db: Session, barcode: str | None, *, existing: str | None = None
) -> str:
    """保存用バーコード。未入力時は新規採番、更新時は既存を維持。"""
    code = coerce_product_barcode(barcode)
    if code:
        return code
    if existing:
        return existing
    return generate_auto_barcode(db)


def get_product_by_barcode(db: Session, barcode: str) -> Product | None:
    code = coerce_product_barcode(barcode)
    if not code:
        return None
    return db.query(Product).filter(Product.barcode == code).first()


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
            joinedload(Product.category).joinedload(Category.shelf_section),
            joinedload(Product.maker),
            joinedload(Product.dealer),
            joinedload(Product.brand),
            joinedload(Product.delivery_codes).joinedload(ProductDeliveryCode.dealer),
        )
        .filter(Product.id == product_id)
        .first()
    )


def create_product(db: Session, data: ProductCreate) -> Product:
    _validate_product_brand(db, data.maker_id, data.brand_id)
    dump = data.model_dump(exclude={"deployment"})
    jan = dump.get("jan_code")
    dump["jan_code"] = (jan or "").strip() or None
    dump["barcode"] = resolve_product_barcode(db, dump.get("barcode"))
    product = Product(**dump)
    db.add(product)
    db.flush()
    apply_product_store_deployment(
        db, product.id, data.deployment.expand_all_stores, data.deployment.store_ids
    )
    db.commit()
    db.refresh(product)
    return product


def update_product(db: Session, product: Product, data: ProductUpdate) -> Product:
    _validate_product_brand(db, data.maker_id, data.brand_id)
    product.name = data.name
    product.barcode = resolve_product_barcode(
        db, data.barcode, existing=product.barcode
    )
    product.jan_code = (data.jan_code or "").strip() or None
    product.unit = data.unit
    product.standard_stock = data.standard_stock
    product.warning_threshold = data.warning_threshold
    product.critical_threshold = data.critical_threshold
    product.category_id = data.category_id
    product.maker_id = data.maker_id
    product.brand_id = data.brand_id
    product.dealer_id = data.dealer_id
    apply_product_store_deployment(
        db, product.id, data.deployment.expand_all_stores, data.deployment.store_ids
    )
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
    if not name:
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
        "stores": col("stores", "store_ids", "展開店舗"),
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
                result.errors.append(f"{row_num}行目: 商品名は必須です")
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
            stores_raw = data.get("stores", "")
        else:
            cells = data
            if len(cells) < 1:
                result.errors.append(f"{row_num}行目: 商品名がありません")
                result.skipped += 1
                continue
            name = cells[0]
            barcode = cells[1] if len(cells) > 1 else ""
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
            stores_raw = (cells[7].strip() if len(cells) > 7 else "") or ""
            base = 8
            for i in range(5):
                d_idx = base + i * 2
                c_idx = d_idx + 1
                dealer_v = cells[d_idx] if len(cells) > d_idx else ""
                code_v = cells[c_idx] if len(cells) > c_idx else ""
                delivery_pairs.append((dealer_v, code_v))

        existing = get_product_by_barcode(db, barcode) if barcode else None
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

            try:
                expand_all, store_ids = parse_stores_column(stores_raw)
                apply_product_store_deployment(db, product.id, expand_all, store_ids)
            except Exception as ex:
                result.errors.append(f"{row_num}行目 展開店舗: {ex}")

        except Exception as e:
            result.errors.append(f"{row_num}行目: {e}")
            result.skipped += 1
            db.rollback()

    return result.model_dump()


# ---------------------------------------------------------------------------
# 在庫
# ---------------------------------------------------------------------------


def require_store_id_for_stock(store_id: int | None) -> int:
    """補充・使用は必ず店舗IDと紐づける"""
    if store_id is None or int(store_id) < 1:
        raise ValueError("店舗を選択してください。")
    return int(store_id)


def format_stock_shortage_message(current_qty: int, unit: str = "本") -> str:
    """使用登録で在庫がマイナスになる場合のメッセージ"""
    u = unit or "本"
    return (
        f"在庫が不足しています。現在の在庫数：{current_qty}{u}。"
        f"使用できる最大数：{current_qty}{u}。"
    )


def assert_use_quantity_allowed(
    current_qty: int, quantity: int, unit: str = "本"
) -> None:
    """使用済み登録: 在庫マイナス禁止"""
    if quantity < 1:
        raise ValueError("数量は1以上を指定してください。")
    if current_qty - quantity < 0:
        raise ValueError(format_stock_shortage_message(current_qty, unit))


INVENTORY_NOT_ON_SHELF_MSG = "この店舗の棚にない商品です。"


def parse_stores_column(raw: str) -> tuple[bool, list[int]]:
    """
    CSV stores 列: 空欄・all → 全店舗 / "1,3,5" → 指定店舗ID
    """
    text = (raw or "").strip().lower()
    if not text or text in ("all", "全店舗", "全店", "*"):
        return True, []
    ids: list[int] = []
    for part in text.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise ValueError(f"店舗IDは数値で指定してください: {part}")
        ids.append(int(part))
    if not ids:
        return True, []
    return False, ids


def get_active_store_ids_for_product(db: Session, product_id: int) -> list[int]:
    rows = (
        db.query(Inventory.store_id)
        .filter(Inventory.product_id == product_id, Inventory.is_active.is_(True))
        .all()
    )
    return [r[0] for r in rows]


def apply_product_store_deployment(
    db: Session,
    product_id: int,
    expand_all_stores: bool,
    store_ids: list[int],
) -> None:
    """選択店舗の inventories.is_active = true、それ以外は false"""
    stores = get_stores(db, active_only=True)
    all_ids = [s.id for s in stores]
    if expand_all_stores:
        active_ids = set(all_ids)
    else:
        active_ids = {sid for sid in store_ids if sid in all_ids}
        unknown = set(store_ids) - active_ids
        if unknown:
            raise ValueError(f"無効な店舗ID: {', '.join(str(x) for x in sorted(unknown))}")

    for sid in all_ids:
        inv = get_or_create_inventory(db, store_id=sid, product_id=product_id, commit=False)
        inv.is_active = sid in active_ids
    db.commit()


def get_inventory_row(
    db: Session, store_id: int, product_id: int
) -> Inventory | None:
    return (
        db.query(Inventory)
        .filter(Inventory.store_id == store_id, Inventory.product_id == product_id)
        .first()
    )


def is_product_on_shelf(db: Session, store_id: int, product_id: int) -> bool:
    inv = get_inventory_row(db, store_id, product_id)
    return inv is not None and inv.is_active


def assert_product_on_shelf_for_use(
    db: Session, store_id: int, product_id: int
) -> Inventory:
    """使用登録: その店舗で is_active であること"""
    inv = get_inventory_row(db, store_id, product_id)
    if not inv or not inv.is_active:
        raise ValueError(INVENTORY_NOT_ON_SHELF_MSG)
    return inv


def activate_inventory_at_store(
    db: Session, store_id: int, product_id: int, *, commit: bool = True
) -> Inventory:
    """補充登録時に棚へ並べる"""
    inv = get_or_create_inventory(
        db, store_id, product_id, commit=False
    )
    inv.is_active = True
    if commit:
        db.commit()
        db.refresh(inv)
    return inv


def get_or_create_inventory(
    db: Session, store_id: int, product_id: int, *, commit: bool = True
) -> Inventory:
    """店舗×商品の在庫レコードを取得（なければ quantity=0, is_active=False で作成）"""
    inv = get_inventory_row(db, store_id, product_id)
    if inv:
        return inv
    inv = Inventory(
        store_id=store_id, product_id=product_id, quantity=0, is_active=False
    )
    db.add(inv)
    if commit:
        db.commit()
        db.refresh(inv)
    else:
        db.flush()
    return inv


def _inventory_item_from_row(
    db: Session,
    store_id: int,
    product: Product,
    inv: Inventory,
    settings_map: dict,
) -> InventoryItemOut:
    warning, critical = resolve_thresholds(product, settings_map.get(product.id))
    level = calc_stock_level(inv.quantity, warning, critical)
    return InventoryItemOut(
        product_id=product.id,
        product_name=product.name,
        barcode=product.barcode,
        unit=product.unit,
        quantity=inv.quantity,
        standard_stock=resolve_standard_stock(product, settings_map.get(product.id)),
        stock_level=level,
        warning_threshold=warning,
        critical_threshold=critical,
        category_id=product.category_id,
        category_name=product.category.name if product.category else "",
        maker_id=product.maker_id,
        maker_name=product.maker.name if product.maker else None,
        brand_id=product.brand_id,
        brand_name=product.brand.name if product.brand else None,
        dealer_id=product.dealer_id,
        dealer_name=product.dealer.name if product.dealer else None,
        is_on_shelf=inv.is_active,
    )


def get_inventory_list(
    db: Session,
    store_id: int,
    category_id: int | None = None,
    *,
    maker_id: int | None = None,
    brand_id: int | None = None,
    section: int | None = None,
    active_only: bool = True,
) -> list[InventoryItemOut]:
    """
    店舗の在庫一覧。
    active_only=True（ダッシュボード）: is_active の商品のみ。
    active_only=False（補充画面の検索）: マスタ全商品＋在庫数。
    """
    settings_map = get_settings_map(db, store_id)
    result: list[InventoryItemOut] = []

    if active_only:
        q = (
            db.query(Inventory)
            .options(
                joinedload(Inventory.product).joinedload(Product.category),
                joinedload(Inventory.product).joinedload(Product.maker),
                joinedload(Inventory.product).joinedload(Product.dealer),
                joinedload(Inventory.product).joinedload(Product.brand),
            )
            .filter(
                Inventory.store_id == store_id,
                Inventory.is_active.is_(True),
            )
        )
        rows = q.all()
        for inv in rows:
            product = inv.product
            if category_id and product.category_id != category_id:
                continue
            if section and (
                not product.category or product.category.section != section
            ):
                continue
            if maker_id and product.maker_id != maker_id:
                continue
            if brand_id and product.brand_id != brand_id:
                continue
            result.append(
                _inventory_item_from_row(db, store_id, product, inv, settings_map)
            )
        result.sort(key=lambda x: x.product_name)
        return result

    products = get_products(
        db,
        category_id=category_id,
        maker_id=maker_id,
        brand_id=brand_id,
        section=section,
    )
    for product in products:
        inv = get_inventory_row(db, store_id, product.id)
        if not inv:
            inv = Inventory(
                store_id=store_id,
                product_id=product.id,
                quantity=0,
                is_active=False,
            )
        result.append(
            _inventory_item_from_row(db, store_id, product, inv, settings_map)
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

    require_store_id_for_stock(data.store_id)

    if data.action == InventoryAction.USE:
        inv = assert_product_on_shelf_for_use(db, data.store_id, product.id)
        assert_use_quantity_allowed(inv.quantity, data.quantity, product.unit)
        inv.quantity -= data.quantity
        action_label = "使用"
    else:
        inv = activate_inventory_at_store(db, data.store_id, product.id, commit=False)
        inv.quantity += data.quantity
        action_label = "補充"

    setting = get_settings_map(db, data.store_id).get(product.id)
    warning, critical = resolve_thresholds(product, setting)
    level = calc_stock_level(inv.quantity, warning, critical)

    log = InventoryLog(
        store_id=data.store_id,
        product_id=product.id,
        user_id=user.id,
        action=data.action,
        quantity_change=data.quantity,
        quantity_after=inv.quantity,
    )
    if data.recorded_at:
        log.created_at = data.recorded_at
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
    since = datetime.now(JST) - timedelta(days=days)
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


def _today_start_utc() -> datetime:
    """当日 0:00（JST）を UTC naive で返す"""
    from datetime import timedelta, timezone

    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    start_jst = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_jst.astimezone(timezone.utc).replace(tzinfo=None)


def _stock_log_row_dict(log: InventoryLog, store_name: str) -> dict:
    return {
        "id": log.id,
        "store_id": log.store_id,
        "store_name": store_name,
        "product_id": log.product_id,
        "product_name": log.product.name if log.product else "",
        "unit": (log.product.unit if log.product else "本") or "本",
        "action": log.action,
        "quantity_change": log.quantity_change,
        "quantity_after": log.quantity_after,
        "created_at": log.created_at,
        "is_edited": bool(getattr(log, "is_edited", False)),
    }


def list_stock_logs(
    db: Session, *, store_id: int, limit: int = 20
) -> list[dict]:
    """補充/使用の登録履歴（最新順）"""
    limit = max(1, min(int(limit or 20), 100))
    logs = (
        db.query(InventoryLog)
        .options(
            joinedload(InventoryLog.product),
            joinedload(InventoryLog.user),
        )
        .filter(InventoryLog.store_id == store_id)
        .order_by(InventoryLog.created_at.desc(), InventoryLog.id.desc())
        .limit(limit)
        .all()
    )
    store = get_store(db, store_id)
    store_name = store.name if store else ""
    return [_stock_log_row_dict(log, store_name) for log in logs]


def list_stock_logs_today(
    db: Session, *, store_id: int, log_type: str
) -> dict:
    """当日（JST 0:00〜現在）の補充 or 使用履歴を全件返す"""
    if log_type == "replenish":
        action = InventoryAction.RESTOCK
    elif log_type == "consume":
        action = InventoryAction.USE
    else:
        raise ValueError("type は replenish または consume を指定してください。")

    start = _today_start_jst()
    store = get_store(db, store_id)
    store_name = store.name if store else ""

    logs = (
        db.query(InventoryLog)
        .options(
            joinedload(InventoryLog.product),
            joinedload(InventoryLog.user),
        )
        .filter(
            InventoryLog.store_id == store_id,
            InventoryLog.action == action,
            InventoryLog.created_at >= start,
        )
        .order_by(InventoryLog.created_at.desc(), InventoryLog.id.desc())
        .all()
    )
    items = [_stock_log_row_dict(log, store_name) for log in logs]
    return {"count": len(items), "store_name": store_name, "items": items}


def edit_stock_log(
    db: Session,
    *,
    log_id: int,
    new_quantity: int,
    reason: str | None,
    editor_user: User,
) -> InventoryLog:
    """在庫ログの数量を修正し、差分を在庫へ反映して修正履歴を残す（管理者のみ想定）"""
    log = (
        db.query(InventoryLog)
        .options(joinedload(InventoryLog.product))
        .filter(InventoryLog.id == log_id)
        .first()
    )
    if not log:
        raise ValueError("ログが見つかりません。")
    product = log.product or get_product_by_id(db, log.product_id)
    if not product:
        raise ValueError("商品が見つかりません。")

    try:
        new_q = int(new_quantity)
    except (TypeError, ValueError):
        raise ValueError("数量が不正です。")
    if new_q < 0:
        raise ValueError("数量は0以上にしてください。")

    old_q = int(log.quantity_change or 0)
    if new_q == old_q and not reason:
        return log

    sign = -1 if log.action == InventoryAction.USE else 1
    delta = sign * (new_q - old_q)

    inv = get_inventory_row(db, log.store_id, log.product_id)
    if not inv:
        inv = Inventory(store_id=log.store_id, product_id=log.product_id, quantity=0, is_active=False)
        db.add(inv)
        db.flush()

    unit = product.unit or "本"
    if inv.quantity + delta < 0:
        raise ValueError(f"在庫が不足しています（現在庫: {inv.quantity}{unit}）。")

    before_after = int(log.quantity_after or 0)
    next_after = before_after + delta
    if next_after < 0:
        raise ValueError(f"在庫が不足しています（現在庫: {inv.quantity}{unit}）。")

    if not getattr(log, "is_edited", False):
        log.original_quantity = old_q

    inv.quantity += delta
    log.quantity_change = new_q
    log.quantity_after = next_after
    log.is_edited = True
    log.edited_at = datetime.now(JST)
    log.edited_by = editor_user.id
    log.edit_reason = (reason or "").strip() or None

    edit = InventoryLogEdit(
        log_id=log.id,
        edited_at=log.edited_at,
        edited_by=editor_user.id,
        before_quantity=old_q,
        after_quantity=new_q,
        edit_reason=log.edit_reason,
    )
    db.add(edit)
    db.commit()
    db.refresh(log)
    return log


def list_inventory_log_edits(db: Session, *, limit: int = 200) -> list[dict]:
    """在庫ログの修正履歴（管理者画面用）"""
    limit = max(1, min(int(limit or 200), 2000))
    rows = (
        db.query(InventoryLogEdit, InventoryLog, Product, Store, User)
        .join(InventoryLog, InventoryLog.id == InventoryLogEdit.log_id)
        .join(Product, Product.id == InventoryLog.product_id)
        .join(Store, Store.id == InventoryLog.store_id)
        .join(User, User.id == InventoryLogEdit.edited_by)
        .order_by(InventoryLogEdit.edited_at.desc(), InventoryLogEdit.id.desc())
        .limit(limit)
        .all()
    )
    out: list[dict] = []
    for edit, log, product, store, user in rows:
        out.append(
            {
                "id": edit.id,
                "log_id": edit.log_id,
                "edited_at": edit.edited_at,
                "edited_by": edit.edited_by,
                "editor_name": user.username if user else None,
                "store_id": store.id if store else log.store_id,
                "store_name": store.name if store else "",
                "product_id": product.id if product else log.product_id,
                "product_name": product.name if product else "",
                "unit": (product.unit if product else "本") or "本",
                "action": log.action,
                "before_quantity": edit.before_quantity,
                "after_quantity": edit.after_quantity,
                "edit_reason": edit.edit_reason,
            }
        )
    return out


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


# ---------------------------------------------------------------------------
# ブランドマスタ（実装は crud_masters — 循環 import 回避のため遅延委譲）
# ---------------------------------------------------------------------------

def get_brands(db: Session, *, maker_id: int | None = None, active_maker_only: bool = True):
    from app import crud_masters

    return crud_masters.get_brands(db, maker_id=maker_id, active_maker_only=active_maker_only)


def get_brand(db: Session, brand_id: int):
    from app import crud_masters

    return crud_masters.get_brand(db, brand_id)


def create_brand(db: Session, data):
    from app import crud_masters

    return crud_masters.create_brand(db, data)


def update_brand(db: Session, brand, data):
    from app import crud_masters

    return crud_masters.update_brand(db, brand, data)


def delete_brand(db: Session, brand) -> None:
    from app import crud_masters

    crud_masters.delete_brand(db, brand)


def brand_to_out(brand, maker_name: str | None = None):
    from app import crud_masters

    return crud_masters.brand_to_out(brand, maker_name=maker_name)


# ---------------------------------------------------------------------------
# 店舗別発注目安（store_product_settings）— 全画面共通
# ---------------------------------------------------------------------------


def get_store_product_setting(db: Session, store_id: int, product_id: int) -> dict:
    from app import crud_store_settings

    return crud_store_settings.get_store_product_setting(db, store_id, product_id)


def upsert_store_product_setting_product(
    db: Session,
    store_id: int,
    product_id: int,
    *,
    standard_stock: int | None,
    warning_threshold: int,
    critical_threshold: int,
):
    from app import crud_store_settings

    return crud_store_settings.upsert_store_product_setting_product(
        db,
        store_id,
        product_id,
        standard_stock=standard_stock,
        warning_threshold=warning_threshold,
        critical_threshold=critical_threshold,
    )
