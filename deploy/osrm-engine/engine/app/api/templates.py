import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TemplateModel
from app.schemas import TemplateCreate, TemplateOut, TemplateUpdate

router = APIRouter()


def _to_out(row: TemplateModel) -> TemplateOut:
    return TemplateOut(id=row.id, name=row.name, config=json.loads(row.config_json), created_at=row.created_at)


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db)) -> list[TemplateOut]:
    rows = db.query(TemplateModel).order_by(TemplateModel.created_at.desc()).all()
    return [_to_out(r) for r in rows]


@router.post("/templates", response_model=TemplateOut)
def create_template(body: TemplateCreate, db: Session = Depends(get_db)) -> TemplateOut:
    row = TemplateModel(
        id=str(uuid.uuid4()),
        name=body.name,
        config_json=json.dumps(body.config),
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.put("/templates/{template_id}", response_model=TemplateOut)
def rename_template(template_id: str, body: TemplateUpdate, db: Session = Depends(get_db)) -> TemplateOut:
    row = db.get(TemplateModel, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    row.name = body.name
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/templates/{template_id}")
def delete_template(template_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(TemplateModel, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}
