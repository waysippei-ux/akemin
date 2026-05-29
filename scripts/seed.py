"""
初期データをデータベースに投入するスクリプト

実行方法（プロジェクトルート salon-color-inventory/ で）:
    python scripts/seed.py

再投入:
    rm -f data/inventory.db && python scripts/seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import crud
from app.database import SessionLocal, init_db
from app.init_data import STORE_STAFF_ACCOUNTS, sync_store_staff_users
from app.models import Category, CategorySection, Inventory, Product, UserRole

# ---------------------------------------------------------------------------
# 店舗名（変更しやすいよう変数で管理）
# ---------------------------------------------------------------------------
STORE_NAMES = ["神宮前本店", "表参道店", "新宿店"]

# ---------------------------------------------------------------------------
# カテゴリ初期データ（section, 名前）
# ---------------------------------------------------------------------------
CATEGORIES_MATERIALS = [
    "カラー剤",
    "シャンプー剤",
    "トリートメント剤",
    "処理剤",
    "ストレートパーマ材",
    "パーマ材",
    "スタイリング剤",
]

CATEGORIES_RETAIL = [
    "シャンプー",
    "トリートメント",
    "アウトバストリートメント",
    "美容機器",
]

PRODUCTS = [
    ("ミルクティー 8Lv", "4901001000001"),
    ("アッシュ 9Lv", "4901001000002"),
    ("ブラック 1Lv", "4901001000003"),
    ("ダークブラウン 4Lv", "4901001000004"),
    ("ライトブラウン 6Lv", "4901001000005"),
    ("ピンクベージュ 8Lv", "4901001000006"),
    ("グレー 7Lv", "4901001000007"),
    ("ベージュ 9Lv", "4901001000008"),
    ("ホワイト 12Lv", "4901001000009"),
    ("オレンジ 10Lv", "4901001000010"),
]

COLOR_CATEGORY_ID = 1
INITIAL_QUANTITY = 5
WARNING_THRESHOLD = 4
CRITICAL_THRESHOLD = 2


def _build_users(store_map: dict[str, int]) -> list[dict]:
    users = [
        {
            "username": "admin",
            "password": "admin123",
            "role": UserRole.ADMIN,
            "store_name": None,
        },
    ]
    for username, password, store_name in STORE_STAFF_ACCOUNTS:
        users.append(
            {
                "username": username,
                "password": password,
                "role": UserRole.STAFF,
                "store_name": store_name,
            }
        )
    return users


def _seed_categories(db) -> None:
    sort = 1
    for name in CATEGORIES_MATERIALS:
        db.add(
            Category(
                name=name,
                section=CategorySection.MATERIALS.value,
                sort_order=sort,
                is_active=True,
            )
        )
        sort = 1
    for name in CATEGORIES_RETAIL:
        db.add(
            Category(
                name=name,
                section=CategorySection.RETAIL.value,
                sort_order=sort,
                is_active=True,
            )
        )
        sort += 1
    db.commit()
    total = len(CATEGORIES_MATERIALS) + len(CATEGORIES_RETAIL)
    print(f"  カテゴリ: {total} 件（材料{len(CATEGORIES_MATERIALS)} / 販売{len(CATEGORIES_RETAIL)}）")


def seed():
    init_db()
    db = SessionLocal()

    try:
        if crud.get_user_by_username(db, "admin"):
            print("⚠️  既に初期データがあります（admin ユーザーが存在します）。")
            print("   スタッフのみ同期: python -c \"from app.database import SessionLocal, init_db; from app.init_data import sync_store_staff_users; init_db(); db=SessionLocal(); sync_store_staff_users(db); db.close()\"")
            return

        print("📦 初期データを投入します...")

        _seed_categories(db)

        store_map: dict[str, int] = {}
        for name in STORE_NAMES:
            store = crud.create_store(db, name)
            store_map[name] = store.id
            print(f"  店舗: {name} (id={store.id})")

        for u in _build_users(store_map):
            store_id = store_map[u["store_name"]] if u["store_name"] else None
            user = crud.create_user(
                db,
                username=u["username"],
                password=u["password"],
                role=u["role"],
                store_id=store_id,
            )
            label = u["store_name"] or "全店舗"
            print(f"  ユーザー: {user.username} ({label})")

        products: list[Product] = []
        for name, barcode in PRODUCTS:
            p = Product(
                name=name,
                barcode=barcode,
                unit="本",
                warning_threshold=WARNING_THRESHOLD,
                critical_threshold=CRITICAL_THRESHOLD,
                category_id=COLOR_CATEGORY_ID,
                maker_id=None,
                dealer_id=None,
            )
            db.add(p)
            products.append(p)
        db.commit()
        for p in products:
            db.refresh(p)
            print(f"  商品: {p.name}（カラー剤 category_id={COLOR_CATEGORY_ID}）")

        for store_name, store_id in store_map.items():
            for product in products:
                db.add(
                    Inventory(
                        store_id=store_id,
                        product_id=product.id,
                        quantity=INITIAL_QUANTITY,
                        is_active=True,
                    )
                )
            print(f"  在庫: {store_name} — {len(products)} SKU × {INITIAL_QUANTITY}本")

        db.commit()
        sync_store_staff_users(db)

        print("\n✅ 初期データの投入が完了しました。")
        print("\nログイン:")
        print("  管理者  admin / admin123")
        for username, password, store_name in STORE_STAFF_ACCOUNTS:
            print(f"  {store_name}  {username} / {password}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
