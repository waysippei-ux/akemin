"""
認証 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud
from app.auth import create_access_token, get_current_user_out
from app.database import get_db
from app.schemas import LoginRequest, Token, UserOut

router = APIRouter()


@router.post("/login", response_model=Token)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """ユーザー名・パスワードでログインし JWT を返す"""
    user = crud.authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザー名またはパスワードが正しくありません。",
        )
    token = create_access_token(data={"sub": user.username})
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def get_me(current_user: UserOut = Depends(get_current_user_out)):
    """ログイン中のユーザー情報"""
    return current_user
