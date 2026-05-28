"""
SQLite データベースへの接続を管理するモジュール
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BASE_DIR, settings


def _sqlite_file_path(url: str) -> Path | None:
    """DATABASE_URL から SQLite ファイルの Path を返す（SQLite 以外は None）"""
    if not url.startswith("sqlite:///"):
        return None
    raw = url.replace("sqlite:///", "", 1)
    if raw.startswith("./"):
        raw = raw[2:]
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def ensure_data_directory() -> None:
    """
    SQLite 用の親ディレクトリを作成する。
    ローカル: data/ 、Render: /data/ など DATABASE_URL に合わせる。
    """
    db_path = _sqlite_file_path(settings.DATABASE_URL)
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)


def _resolve_sqlite_path(url: str) -> str:
    """
    sqlite:///./data/inventory.db や sqlite:////data/inventory.db を
    絶対パスに正規化し、親ディレクトリを自動作成する
    """
    path = _sqlite_file_path(url)
    if path is None:
        return url
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


DATABASE_URL = _resolve_sqlite_path(settings.DATABASE_URL)

# SQLite はマルチスレッド用の設定が必要
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """全テーブルが継承するベースクラス"""
    pass


def get_db():
    """
    API ごとに DB セッションを開いて、終わったら閉じる
    FastAPI の Depends で使う
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _table_column_names(insp, table: str) -> set[str]:
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _column_is_nullable(insp, table: str, column: str) -> bool | None:
    if table not in insp.get_table_names():
        return None
    for col in insp.get_columns(table):
        if col["name"] == column:
            return col.get("nullable")
    return None


def _ensure_brands_table(engine, insp) -> None:
    """
    brands テーブルを用意する。
    ・存在しなければ CREATE TABLE（SQLAlchemy / dialect 準拠）
    ・存在すれば不足列を ALTER TABLE で追加
    ・maker_id は NULL 許可へ（DROP NOT NULL）
    """
    from sqlalchemy import inspect, text

    from app.models import Brand

    if "brands" not in insp.get_table_names():
        Brand.__table__.create(bind=engine, checkfirst=True)
        return

    brand_cols = _table_column_names(insp, "brands")
    with engine.begin() as conn:
        if "name" not in brand_cols:
            conn.execute(
                text(
                    "ALTER TABLE brands ADD COLUMN name VARCHAR(100) NOT NULL DEFAULT ''"
                )
            )
        if "maker_id" not in brand_cols:
            conn.execute(
                text(
                    "ALTER TABLE brands ADD COLUMN maker_id INTEGER "
                    "REFERENCES makers(id)"
                )
            )
        if "sort_order" not in brand_cols:
            conn.execute(
                text(
                    "ALTER TABLE brands ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
                )
            )

    # 列追加後に再取得（既存列が NOT NULL のときのみ緩和）
    insp = inspect(engine)
    if (
        engine.dialect.name == "postgresql"
        and _column_is_nullable(insp, "brands", "maker_id") is False
    ):
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE brands ALTER COLUMN maker_id DROP NOT NULL")
            )


def _migrate_products_columns(engine, insp) -> None:
    """products に不足列を ALTER TABLE で追加（brand_id は brands 作成後に追加）"""
    from sqlalchemy import text

    cols = _table_column_names(insp, "products")
    need_category_id = "category_id" not in cols
    alters: list[str] = []
    if need_category_id:
        alters.append("ALTER TABLE products ADD COLUMN category_id INTEGER")
    if "maker_id" not in cols:
        alters.append("ALTER TABLE products ADD COLUMN maker_id INTEGER")
    if "dealer_id" not in cols:
        alters.append("ALTER TABLE products ADD COLUMN dealer_id INTEGER")
    # brand_id: 列が無い場合のみ追加（PostgreSQL でも inspect で存在確認）
    if "brand_id" not in cols:
        alters.append(
            "ALTER TABLE products ADD COLUMN brand_id INTEGER REFERENCES brands(id)"
        )

    if not alters:
        return

    with engine.begin() as conn:
        for sql in alters:
            conn.execute(text(sql))
        if need_category_id:
            conn.execute(
                text("UPDATE products SET category_id = 1 WHERE category_id IS NULL")
            )


def migrate_schema() -> None:
    """
    既存 DB への列追加（後方互換）。
    create_all だけでは既存テーブルに列が足されないため ALTER TABLE する。
    PostgreSQL / SQLite 双方で動作する DDL を使用する。
    """
    from sqlalchemy import inspect, text

    from app import models  # noqa: F401

    insp = inspect(engine)

    # brands を先に用意（products.brand_id の FK 参照先）
    _ensure_brands_table(engine, insp)
    insp = inspect(engine)

    if "products" in insp.get_table_names():
        _migrate_products_columns(engine, insp)
        insp = inspect(engine)

    if "categories" in insp.get_table_names():
        cat_cols = {c["name"] for c in insp.get_columns("categories")}
        if "section" not in cat_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE categories ADD COLUMN section INTEGER NOT NULL DEFAULT 1"
                    )
                )

    if "stores" in insp.get_table_names():
        store_cols = {c["name"] for c in insp.get_columns("stores")}
        if "is_active" not in store_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE stores ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true"
                    )
                )

    if "products" in insp.get_table_names():
        prod_cols = {c["name"] for c in insp.get_columns("products")}
        if "jan_code" not in prod_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE products ADD COLUMN jan_code VARCHAR(50)"))
        if "standard_stock" not in prod_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE products ADD COLUMN standard_stock INTEGER NOT NULL DEFAULT 0"
                    )
                )

    # 店舗別発注目安（新規テーブルのみ作成・既存テーブルは変更しない）
    if "store_product_settings" not in insp.get_table_names():
        models.StoreProductSetting.__table__.create(bind=engine, checkfirst=True)

    if "inventories" in insp.get_table_names():
        inv_cols = {c["name"] for c in insp.get_columns("inventories")}
        if "is_active" not in inv_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE inventories ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT false"
                    )
                )
                # 既存データは棚に並んでいるものとして有効化
                conn.execute(text("UPDATE inventories SET is_active = true"))

    # 在庫ログ: 修正情報カラム追加
    if "inventory_logs" in insp.get_table_names():
        log_cols = {c["name"] for c in insp.get_columns("inventory_logs")}
        alters: list[str] = []
        if "edited_at" not in log_cols:
            alters.append("ALTER TABLE inventory_logs ADD COLUMN edited_at TIMESTAMP")
        if "edited_by" not in log_cols:
            alters.append("ALTER TABLE inventory_logs ADD COLUMN edited_by INTEGER")
        if "original_quantity" not in log_cols:
            alters.append("ALTER TABLE inventory_logs ADD COLUMN original_quantity INTEGER")
        if "edit_reason" not in log_cols:
            alters.append("ALTER TABLE inventory_logs ADD COLUMN edit_reason VARCHAR(255)")
        if "is_edited" not in log_cols:
            alters.append(
                "ALTER TABLE inventory_logs ADD COLUMN is_edited BOOLEAN NOT NULL DEFAULT false"
            )
        if alters:
            with engine.begin() as conn:
                for sql in alters:
                    conn.execute(text(sql))

    # 在庫ログ修正履歴テーブル（新規）
    if "inventory_log_edits" not in insp.get_table_names():
        models.InventoryLogEdit.__table__.create(bind=engine, checkfirst=True)

    if "categories" in insp.get_table_names():
        cat_cols = {c["name"] for c in insp.get_columns("categories")}
        if "sort_order" not in cat_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE categories ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
                    )
                )

    _ensure_default_sections(engine, insp)
    _ensure_direct_dealer(engine, insp)


def _ensure_direct_dealer(engine, insp) -> None:
    """直取引用ディーラー「メーカー直」を自動作成"""
    from sqlalchemy import text

    from app.constants import DIRECT_DEALER_NAME

    if "dealers" not in insp.get_table_names():
        return

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM dealers WHERE name = :n LIMIT 1"),
            {"n": DIRECT_DEALER_NAME},
        ).fetchone()
        if row:
            return
        conn.execute(
            text(
                "INSERT INTO dealers (name, contact_info, is_active) "
                "VALUES (:n, NULL, true)"
            ),
            {"n": DIRECT_DEALER_NAME},
        )


def _ensure_default_sections(engine, insp) -> None:
    """棚マスタ（材料の棚・店販の棚）を初期投入"""
    from sqlalchemy import text

    from app.models import CategorySection

    if "sections" not in insp.get_table_names():
        return

    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM sections")).scalar()
        if count and count > 0:
            return
        conn.execute(
            text(
                "INSERT INTO sections (id, name, color, sort_order, is_active) "
                "VALUES (:id1, :n1, :c1, 1, true), (:id2, :n2, :c2, 2, true)"
            ),
            {
                "id1": CategorySection.MATERIALS.value,
                "n1": "材料の棚",
                "c1": "#eae9fd",
                "id2": CategorySection.RETAIL.value,
                "n2": "店販の棚",
                "c2": "#e4f2f6",
            },
        )


def init_db():
    """テーブルを作成し、既存 DB をマイグレーションする"""
    from app import models  # noqa: F401

    ensure_data_directory()
    Base.metadata.create_all(bind=engine)
    migrate_schema()
