"""
ログイン・JWT・権限チェック
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, UserRole
from app.schemas import UserOut

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ---------------------------------------------------------------------------
# パスワード
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# 現在のユーザー取得（Depends 用）
# ---------------------------------------------------------------------------

def extract_access_token(request: Request, bearer: Optional[str] = None) -> Optional[str]:
    """Authorization ヘッダーまたは access_token Cookie から JWT を取得"""
    if bearer:
        return bearer
    cookie = request.cookies.get("access_token")
    if cookie:
        return cookie
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def _user_from_token(db: Session, token: str) -> Optional[User]:
    payload = decode_token(token)
    if payload is None:
        return None
    username: str | None = payload.get("sub")
    if username is None:
        return None
    from app import crud

    return crud.get_user_by_username(db, username)


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
    bearer: Optional[str] = Depends(oauth2_scheme),
) -> Optional[User]:
    """ログイン済みなら User、未認証なら None（HTML 画面用）"""
    token = extract_access_token(request, bearer)
    if not token:
        return None
    return _user_from_token(db, token)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    bearer: Optional[str] = Depends(oauth2_scheme),
) -> User:
    """API 用 — Bearer または Cookie 必須"""
    token = extract_access_token(request, bearer)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証されていません",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = _user_from_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証に失敗しました。再度ログインしてください。",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user_out(
    current_user: User = Depends(get_current_user),
) -> UserOut:
    return UserOut.model_validate(current_user)


def is_admin(current_user: User) -> bool:
    return current_user.role == UserRole.ADMIN


def get_allowed_store_ids(current_user: User) -> Optional[List[int]]:
    """None は全店舗アクセス可（管理者）"""
    if is_admin(current_user):
        return None
    if current_user.store_id is not None:
        return [current_user.store_id]
    return []


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """管理者のみ許可"""
    if not is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理者権限が必要です",
        )
    return current_user


def check_store_access(current_user: User, store_id: int) -> bool:
    """
    スタッフは自分の店舗のみ、管理者は全店舗OK。
    権限がなければ 403 を投げる。
    """
    if is_admin(current_user):
        return True
    if current_user.store_id != store_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="この店舗の情報にアクセスする権限がありません",
        )
    return True
