"""
アケミンに相談 — AI チャット画面・API
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import crud
from app.auth import check_store_access, get_current_user
from app.config import BASE_DIR
from app.database import get_db
from app.dependencies import resolve_user_from_request
from app.models import User, UserRole
from app.services.ai_chat import chat_with_akemin

templates = Jinja2Templates(directory=str((BASE_DIR / "templates").resolve()))

router = APIRouter(tags=["アケミンAI"])
api_router = APIRouter(tags=["アケミンAI API"])


class AiChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    store_id: int = Field(..., gt=0)


class AiChatResponse(BaseModel):
    reply: str


def _stores_for_template(db: Session, current_user: User | None) -> list[dict]:
    if current_user and current_user.role == UserRole.STAFF and current_user.store_id:
        store = crud.get_store(db, current_user.store_id)
        if store and store.is_active:
            return [{"id": store.id, "name": store.name}]
        return []
    return [{"id": s.id, "name": s.name} for s in crud.get_all_stores(db, active_only=True)]


@router.get("/ai-chat")
def ai_chat_page(
    request: Request,
    db: Session = Depends(get_db),
):
    """ログイン済み全員が利用可能（HTML は Cookie / localStorage で API 認証）"""
    current_user = resolve_user_from_request(request, db)
    stores = _stores_for_template(db, current_user)
    default_store_id = None
    user_role = ""
    user_store_id = None
    if current_user:
        user_role = current_user.role.value
        user_store_id = current_user.store_id
        if current_user.role == UserRole.STAFF and current_user.store_id:
            default_store_id = current_user.store_id
        elif stores:
            default_store_id = stores[0]["id"]

    return templates.TemplateResponse(
        request,
        "ai_chat.html",
        {
            "stores": stores,
            "user_role": user_role,
            "user_store_id": user_store_id,
            "default_store_id": default_store_id,
            "store_select_disabled": bool(
                current_user
                and current_user.role == UserRole.STAFF
                and current_user.store_id
            ),
        },
    )


@api_router.post("/ai-chat", response_model=AiChatResponse)
def ai_chat_api(
    body: AiChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """在庫データをコンテキストに Claude で返答"""
    check_store_access(current_user, body.store_id)
    if not crud.get_store(db, body.store_id):
        raise HTTPException(status_code=404, detail="店舗が見つかりません。")

    try:
        reply = chat_with_akemin(db, body.store_id, body.message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return AiChatResponse(reply=reply)
