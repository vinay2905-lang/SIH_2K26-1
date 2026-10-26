from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import Institution, User
from ..pipeline.rules_engine import CATEGORIES, OPS, SEVERITIES
from ..pipeline.templates import DOC_TYPES
from ..pipeline.verify import STATUSES
from ..security import create_token, current_user, verify_password
from .serializers import APP_TYPES, institution_json, user_json

router = APIRouter(prefix="/api", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.username == body.username.strip().lower())).scalar()
    if user is None or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong username or password")
    audit.record("Signed in", "user", user.username, user=user)
    return {"token": create_token(user), "user": _me(user, db)}


def _me(user: User, db: Session) -> dict:
    out = user_json(user)
    if user.institution_id:
        out["institution"] = institution_json(db.get(Institution, user.institution_id))
    return out


@router.get("/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _me(user, db)


@router.get("/auth/demo-users")
def demo_users(db: Session = Depends(get_db)):
    """Synthetic demo accounts listed on the sign-in page (sandbox only)."""
    users = db.execute(select(User).where(User.active.is_(True)).order_by(User.role, User.username)).scalars().all()
    out = []
    for u in users:
        item = {"username": u.username, "full_name": u.full_name, "role": u.role}
        if u.institution_id:
            item["institution"] = db.get(Institution, u.institution_id).name
        out.append(item)
    return out


@router.get("/meta")
def meta():
    return {"doc_types": DOC_TYPES, "app_types": APP_TYPES, "operators": OPS, "severities": SEVERITIES,
            "categories": CATEGORIES, "verification_statuses": STATUSES}
