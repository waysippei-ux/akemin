"""
初期データ・スタッフアカウントの同期

起動時（init_db）および scripts/seed.py から利用する。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import Store, User, UserRole

LEGACY_STAFF_USERNAMES = ("staff_a", "staff_b", "staff_c", "staff_d", "staff_e")

# username, password, 店舗名（stores.name と一致させる）
STORE_STAFF_ACCOUNTS = (
    ("ways_a", "ways01", "神宮前本店"),
    ("ways_b", "ways02", "表参道店"),
    ("ways_c", "ways03", "新宿店"),
)


def _find_store_id_by_name(db: Session, name: str) -> int | None:
    store = db.query(Store).filter(Store.name == name).first()
    if store:
        return store.id
    store = (
        db.query(Store)
        .filter(Store.name.contains(name.replace("店", "")))
        .order_by(Store.id)
        .first()
    )
    return store.id if store else None


def sync_store_staff_users(db: Session) -> None:
    """
    ① 旧 staff_a〜e を削除
    ② ways_a / ways_b / ways_c を各店舗に紐づけて作成または更新
    """
    if db.query(User).count() == 0:
        return

    db.query(User).filter(User.username.in_(LEGACY_STAFF_USERNAMES)).delete(
        synchronize_session=False
    )

    for username, password, store_name in STORE_STAFF_ACCOUNTS:
        store_id = _find_store_id_by_name(db, store_name)
        if store_id is None:
            print(
                f"[init_data] 警告: 店舗「{store_name}」が見つからないため "
                f"ユーザー {username} をスキップします。"
            )
            continue

        user = db.query(User).filter(User.username == username).first()
        hashed = hash_password(password)
        if user:
            user.hashed_password = hashed
            user.role = UserRole.STAFF
            user.store_id = store_id
        else:
            db.add(
                User(
                    username=username,
                    hashed_password=hashed,
                    role=UserRole.STAFF,
                    store_id=store_id,
                )
            )

    db.commit()
