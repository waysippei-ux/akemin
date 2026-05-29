"""
認証 API
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app import crud
from app.auth import (
    ACCESS_TOKEN_COOKIE,
    cookie_max_age_seconds,
    create_access_token,
    get_current_user_out,
)
from app.database import get_db
from app.schemas import LoginRequest, Token, UserOut

router = APIRouter()


def _set_auth_cookie(response: Response, token: str) -> None:
    """ブラウザ遷移（HTML）でも認証できるよう HttpOnly Cookie を付与"""
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        max_age=cookie_max_age_seconds(),
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=Token)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """ユーザー名・パスワードでログインし JWT を返す（JSON + Cookie）"""
    user = crud.authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザー名またはパスワードが正しくありません。",
        )
    token = create_access_token(data={"sub": user.username})
    _set_auth_cookie(response, token)
    return Token(access_token=token)


@router.post("/logout", status_code=204)
def logout(response: Response):
    """Cookie を削除（クライアントは localStorage もクリアすること）"""
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def get_me(current_user: UserOut = Depends(get_current_user_out)):
    """ログイン中のユーザー情報"""
    return current_user
