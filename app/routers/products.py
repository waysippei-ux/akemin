"""
商品（カラー材）API — 管理者向け CRUD・CSVインポート
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app import crud, crud_masters
from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User
from app.schemas import (
    ProductCreate,
    ProductDeliveryCodeCreate,
    ProductDeliveryCodeOut,
    ProductImportResult,
    ProductOut,
    ProductUpdate,
)

router = APIRouter()


@router.get("", response_model=list[ProductOut])
def list_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """商品マスタ一覧（ログイン必須）"""
    return [crud_masters.product_to_out(p) for p in crud.get_products(db)]


@router.post("/import/csv", response_model=ProductImportResult)
async def import_products_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """CSV で商品を一括登録・更新（管理者のみ）"""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV ファイル（.csv）を選択してください。",
        )

    raw = await file.read()
    text = None
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ファイルの文字コードを読み取れません（UTF-8 推奨）。",
        )

    return crud.import_products_csv(db, text)


@router.get("/{product_id}/delivery-codes", response_model=list[ProductDeliveryCodeOut])
def list_delivery_codes(
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    product = crud.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品が見つかりません。")
    rows = crud.list_product_delivery_codes(db, product_id)
    return [crud_masters.delivery_code_to_out(r) for r in rows]


@router.post(
    "/{product_id}/delivery-codes",
    response_model=ProductDeliveryCodeOut,
    status_code=status.HTTP_201_CREATED,
)
def add_delivery_code(
    product_id: int,
    body: ProductDeliveryCodeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    product = crud.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品が見つかりません。")
    try:
        row = crud.create_product_delivery_code(
            db,
            product_id,
            body.dealer_id,
            body.delivery_code,
            body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    row = crud.get_product_delivery_code(db, row.id)
    return crud_masters.delivery_code_to_out(row)


@router.delete(
    "/{product_id}/delivery-codes/{code_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_delivery_code(
    product_id: int,
    code_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    row = crud.get_product_delivery_code(db, code_id)
    if not row or row.product_id != product_id:
        raise HTTPException(status_code=404, detail="納品コードが見つかりません。")
    crud.deactivate_product_delivery_code(db, row)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """商品1件取得（管理者のみ）"""
    product = crud.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品が見つかりません。")
    return crud_masters.product_to_out(product, include_delivery_codes=True)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product_endpoint(
    body: ProductCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """商品を新規登録（管理者のみ）"""
    if body.critical_threshold > body.warning_threshold:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="危険閾値は警告閾値以下にしてください。",
        )
    if crud.get_product_by_barcode(db, body.barcode):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="このバーコードは既に登録されています。",
        )
    p = crud.create_product(db, body)
    p = crud.get_product_by_id(db, p.id)
    return crud_masters.product_to_out(p)


@router.put("/{product_id}", response_model=ProductOut)
def update_product_endpoint(
    product_id: int,
    body: ProductUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """商品を更新（管理者のみ）"""
    product = crud.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品が見つかりません。")

    other = crud.get_product_by_barcode(db, body.barcode)
    if other and other.id != product_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="このバーコードは別の商品で使用されています。",
        )

    if body.critical_threshold > body.warning_threshold:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="危険閾値は警告閾値以下にしてください。",
        )

    crud.update_product(db, product, body)
    product = crud.get_product_by_id(db, product_id)
    return crud_masters.product_to_out(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_endpoint(
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """商品を削除（管理者のみ）— 関連在庫・ログも削除"""
    product = crud.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品が見つかりません。")
    crud.delete_product(db, product)
