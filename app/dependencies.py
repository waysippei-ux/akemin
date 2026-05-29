"""
FastAPI Depends 用の認証依存関係（app.auth をラップ）
"""
from app.auth import (
    check_store_access,
    extract_access_token,
    get_current_user,
    get_optional_user,
    is_admin,
    require_admin,
    resolve_user_from_request,
)

__all__ = [
    "check_store_access",
    "extract_access_token",
    "get_current_user",
    "get_optional_user",
    "is_admin",
    "require_admin",
    "resolve_user_from_request",
]
