"""
SQLite データベースへの接続を管理するモジュール
"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BASE_DIR, settings


def _resolve_sqlite_path(url: str) -> str:
    """
    sqlite:///./data/inventory.db のような相対パスを
    プロジェクトルート基準の絶対パスに変換する
    """
    if not url.startswith("sqlite:///"):
        return url

    db_path = url.replace("sqlite:///", "", 1)
    if db_path.startswith("./"):
        absolute = BASE_DIR / db_path[2:]
        absolute.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{absolute}"

    return url


DATABASE_URL = _resolve_sqlite_path(settings.DATABASE_URL)

# SQLite はマルチスレッド用の設定が必要
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
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


def migrate_schema() -> None:
    """
    既存 SQLite DB への列追加（後方互換）
    create_all だけでは既存テーブルに列が足されないため ALTER TABLE する
    """
    from sqlalchemy import inspect, text

    from app import models  # noqa: F401

    insp = inspect(engine)
    if "products" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("products")}
    alters = []
    if "category_id" not in cols:
        alters.append("ALTER TABLE products ADD COLUMN category_id INTEGER")
    if "maker_id" not in cols:
        alters.append("ALTER TABLE products ADD COLUMN maker_id INTEGER")
    if "dealer_id" not in cols:
        alters.append("ALTER TABLE products ADD COLUMN dealer_id INTEGER")

    if alters:
        with engine.begin() as conn:
            for sql in alters:
                conn.execute(text(sql))
            conn.execute(
                text("UPDATE products SET category_id = 1 WHERE category_id IS NULL")
            )

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
                        "ALTER TABLE stores ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
                    )
                )

    if "products" in insp.get_table_names():
        prod_cols = {c["name"] for c in insp.get_columns("products")}
        if "jan_code" not in prod_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE products ADD COLUMN jan_code VARCHAR(50)"))


def init_db():
    """テーブルを作成し、既存 DB をマイグレーションする"""
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_schema()
