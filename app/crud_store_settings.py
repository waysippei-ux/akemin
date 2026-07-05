"""
店舗別発注目安（StoreProductSetting）の CRUD
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Product, Store, StoreProductSetting


def get_settings_map(db: Session, store_id: int) -> dict[int, StoreProductSetting]:
    rows = (
        db.query(StoreProductSetting)
        .filter(StoreProductSetting.store_id == store_id)
        .all()
    )
    return {r.product_id: r for r in rows}


def resolve_standard_stock(
    product: Product, setting: StoreProductSetting | None
) -> int:
    """店舗別 standard_stock を優先し、未設定なら商品マスタのデフォルト"""
    if setting is not None and setting.standard_stock is not None:
        return int(setting.standard_stock)
    return int(getattr(product, "standard_stock", 0) or 0)


def effective_standard_stock_gt_zero(store_id: int):
    """店舗設定優先の標準在庫数が 1 以上（棚を見る表示用）"""
    from sqlalchemy import func

    return func.coalesce(StoreProductSetting.standard_stock, Product.standard_stock, 0) > 0


def outerjoin_store_settings(query, store_id: int):
    """Product 結合済みクエリに店舗別設定を outer join"""
    return query.outerjoin(
        StoreProductSetting,
        (StoreProductSetting.product_id == Product.id)
        & (StoreProductSetting.store_id == store_id),
    )


def resolve_thresholds(
    product: Product, setting: StoreProductSetting | None
) -> tuple[int, int]:
    """店舗別設定を優先し、未設定項目は商品マスタのデフォルトを使う"""
    if setting is None:
        return product.warning_threshold, product.critical_threshold
    warning = (
        setting.warning_threshold
        if setting.warning_threshold is not None
        else product.warning_threshold
    )
    critical = (
        setting.critical_threshold
        if setting.critical_threshold is not None
        else product.critical_threshold
    )
    return warning, critical


def _standard_stock_display(
    product: Product, setting: StoreProductSetting | None
) -> int | None:
    """モーダル入力欄に表示する標準在庫数（店舗設定 → マスタ → 空）"""
    default_std = int(getattr(product, "standard_stock", 0) or 0)
    if setting is not None and setting.standard_stock is not None:
        return int(setting.standard_stock)
    if default_std > 0:
        return default_std
    return None


def _product_setting_core(
    product: Product, setting: StoreProductSetting | None
) -> dict:
    """店舗×商品の発注目安 — 一覧・モーダル共通の算出"""
    default_std = int(getattr(product, "standard_stock", 0) or 0)
    custom_std = (
        int(setting.standard_stock)
        if setting is not None and setting.standard_stock is not None
        else None
    )
    effective_w, effective_c = resolve_thresholds(product, setting)
    effective_std = resolve_standard_stock(product, setting)
    return {
        "standard_stock": _standard_stock_display(product, setting),
        "effective_standard_stock": effective_std,
        "default_standard_stock": default_std,
        "custom_standard_stock": custom_std,
        "warning_threshold": effective_w,
        "critical_threshold": effective_c,
        "default_warning_threshold": product.warning_threshold,
        "default_critical_threshold": product.critical_threshold,
        "effective_warning_threshold": effective_w,
        "effective_critical_threshold": effective_c,
        "custom_warning_threshold": setting.warning_threshold if setting else None,
        "custom_critical_threshold": setting.critical_threshold if setting else None,
        "has_custom_setting": setting is not None,
        "setting_id": setting.id if setting else None,
    }


def get_setting(
    db: Session, store_id: int, product_id: int
) -> StoreProductSetting | None:
    return (
        db.query(StoreProductSetting)
        .filter(
            StoreProductSetting.store_id == store_id,
            StoreProductSetting.product_id == product_id,
        )
        .first()
    )


def get_store_product_setting(
    db: Session, store_id: int, product_id: int
) -> dict:
    """店舗×商品の発注目安を1件取得（store_product_settings 優先）"""
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise ValueError("店舗が見つかりません。")
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise ValueError("商品が見つかりません。")

    setting = get_setting(db, store_id, product_id)
    core = _product_setting_core(product, setting)
    return {
        "store_id": store_id,
        "product_id": product_id,
        "product_name": product.name,
        "unit": product.unit or "本",
        **core,
    }


def upsert_store_product_setting_product(
    db: Session,
    store_id: int,
    product_id: int,
    *,
    standard_stock: int | None,
    warning_threshold: int,
    critical_threshold: int,
) -> StoreProductSetting:
    """store_product_settings を UPSERT（store_id + product_id で一意）"""
    if critical_threshold > warning_threshold:
        raise ValueError("危険閾値（赤）は警告閾値（黄）以下にしてください。")

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise ValueError("商品が見つかりません。")

    row = get_setting(db, store_id, product_id)
    if row:
        row.warning_threshold = warning_threshold
        row.critical_threshold = critical_threshold
        row.standard_stock = standard_stock
    else:
        row = StoreProductSetting(
            store_id=store_id,
            product_id=product_id,
            warning_threshold=warning_threshold,
            critical_threshold=critical_threshold,
            standard_stock=standard_stock,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def upsert_store_product_setting(
    db: Session,
    store_id: int,
    product_id: int,
    warning_threshold: int,
    critical_threshold: int,
    *,
    standard_stock: int | None = None,
    clear_standard_stock: bool = False,
) -> StoreProductSetting:
    """後方互換 — 統一 UPSERT へ委譲"""
    std = None if clear_standard_stock else standard_stock
    return upsert_store_product_setting_product(
        db,
        store_id,
        product_id,
        standard_stock=std,
        warning_threshold=warning_threshold,
        critical_threshold=critical_threshold,
    )


def list_store_product_settings(db: Session, store_id: int) -> list[dict]:
    """店舗の全商品について、デフォルト・有効値・カスタム設定を返す"""
    from app.crud import get_products

    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        return []

    settings_map = get_settings_map(db, store_id)
    products = get_products(db)
    rows: list[dict] = []

    for product in products:
        setting = settings_map.get(product.id)
        core = _product_setting_core(product, setting)
        rows.append(
            {
                "store_id": store_id,
                "store_name": store.name,
                "product_id": product.id,
                "product_name": product.name,
                "barcode": product.barcode,
                "standard_stock": core["effective_standard_stock"],
                "category_id": product.category_id,
                "category_name": product.category.name if product.category else "",
                "maker_id": product.maker_id,
                "maker_name": product.maker.name if product.maker else None,
                "brand_id": product.brand_id,
                "brand_name": product.brand.name if product.brand else None,
                "dealer_id": product.dealer_id,
                "dealer_name": product.dealer.name if product.dealer else None,
                "unit": product.unit,
                "default_standard_stock": core["default_standard_stock"],
                "custom_standard_stock": core["custom_standard_stock"],
                "default_warning_threshold": core["default_warning_threshold"],
                "default_critical_threshold": core["default_critical_threshold"],
                "effective_warning_threshold": core["effective_warning_threshold"],
                "effective_critical_threshold": core["effective_critical_threshold"],
                "custom_warning_threshold": core["custom_warning_threshold"],
                "custom_critical_threshold": core["custom_critical_threshold"],
                "has_custom_setting": core["has_custom_setting"],
                "setting_id": core["setting_id"],
            }
        )
    return rows


def delete_store_product_setting(db: Session, store_id: int, product_id: int) -> bool:
    """店舗別設定を削除し、商品マスタのデフォルトに戻す"""
    row = get_setting(db, store_id, product_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True
