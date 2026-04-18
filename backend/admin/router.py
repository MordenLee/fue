"""API routes for admin tasks (seed data, etc.)."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from providers.models import AIModel, Provider

router = APIRouter(prefix="/api/admin", tags=["admin"])

# shared/providers.json 相对于此文件的绝对路径
_PROVIDERS_JSON = (
    Path(__file__).resolve().parent.parent.parent / "shared" / "providers.json"
)


class SeedResponse(BaseModel):
    message: str
    created_providers: int
    created_models: int
    updated_api_keys: int
    skipped_providers: int


@router.post("/seed", response_model=SeedResponse)
def seed_providers(db: Session = Depends(get_db)):
    """Upsert preset providers from shared/providers.json.
    - 新增：创建供应商及其模型。
    - 已存在：仅当 JSON 中 api_key 非空时更新密鑰，其余字段不覆盖。"""

    if not _PROVIDERS_JSON.exists():
        raise HTTPException(status_code=404, detail="Preset data file not found. Please ensure shared/providers.json exists")

    data: list[dict] = json.loads(_PROVIDERS_JSON.read_text(encoding="utf-8"))

    created_providers = 0
    created_models = 0
    updated_api_keys = 0
    skipped_providers = 0

    for entry in data:
        models_data: list[dict] = entry.pop("models", [])
        api_key: str = entry.get("api_key") or ""

        existing = db.query(Provider).filter(Provider.name == entry["name"]).first()
        if existing:
            if api_key and existing.api_key != api_key:
                existing.api_key = api_key
                updated_api_keys += 1
            else:
                skipped_providers += 1
            continue

        provider = Provider(**entry)
        db.add(provider)
        db.flush()

        for m in models_data:
            db.add(AIModel(provider_id=provider.id, **m))
            created_models += 1

        created_providers += 1

    db.commit()

    return SeedResponse(
        message="Seed complete",
        created_providers=created_providers,
        created_models=created_models,
        updated_api_keys=updated_api_keys,
        skipped_providers=skipped_providers,
    )
