"""
FastAPI アプリケーションのエントリーポイント

起動方法（プロジェクトルートで）:
    uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR
from app.database import init_db

# 静的ファイル・HTMLテンプレートのパス（プロジェクトルート基準の絶対パス）
STATIC_DIR = (BASE_DIR / "static").resolve()
TEMPLATES_DIR = (BASE_DIR / "templates").resolve()

# フォルダがなくても作成し、常に /static をマウントする
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリ起動時・終了時の処理"""
    init_db()
    yield


app = FastAPI(
    title="AKEMIN - サロン在庫管理システム",
    description="美容室のカラー材在庫をバーコードで管理するWebアプリ",
    lifespan=lifespan,
)

# CSS / JavaScript（exists() チェックは使わない — 起動時に未作成だと永続的に404になる）
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# 画面（HTML）— テンプレートは後で作成
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    """トップはログイン画面へ"""
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/dashboard")
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/scan")
def scan_page(request: Request):
    return templates.TemplateResponse(request, "scan.html")


@app.get("/admin/products")
def admin_products_page(request: Request):
    return templates.TemplateResponse(request, "admin_products.html")


@app.get("/orders")
def orders_page(request: Request):
    return templates.TemplateResponse(request, "orders.html")


# ---------------------------------------------------------------------------
# API ルーター
# ---------------------------------------------------------------------------
from app.routers import (
    analysis,
    auth,
    categories,
    dashboard,
    dealers,
    inventory,
    makers,
    orders,
    products,
    stores,
)

app.include_router(auth.router, prefix="/api/auth", tags=["認証"])
app.include_router(stores.router, prefix="/api/stores", tags=["店舗"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["ダッシュボード"])
app.include_router(categories.router, prefix="/api/categories", tags=["カテゴリ"])
app.include_router(dealers.router, prefix="/api/dealers", tags=["ディーラー"])
app.include_router(makers.router, prefix="/api/makers", tags=["メーカー"])
app.include_router(products.router, prefix="/api/products", tags=["商品"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["在庫"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["AI分析"])
app.include_router(orders.router, prefix="/api/orders", tags=["発注"])


@app.get("/health")
def health_check():
    """動作確認用"""
    return {"status": "ok"}
