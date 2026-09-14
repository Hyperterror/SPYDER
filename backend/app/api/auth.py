from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user,
)
from app.models.user import User
from app.services.audit_svc import create_audit_event
import uuid

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db), request: Request = None):
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access = create_access_token(str(user.id), user.role)
    refresh = create_refresh_token(str(user.id))

    create_audit_event(
        db=db,
        event_type="USER_LOGIN",
        actor_user_id=str(user.id),
        metadata={"email": user.email, "role": user.role},
        ip_address=str(request.client.host) if request and request.client else None,
    )

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user={
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        },
    )


@router.post("/refresh")
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.query(User).filter(User.id == payload["sub"], User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access = create_access_token(str(user.id), user.role)
    return {"access_token": access, "token_type": "bearer"}


@router.post("/logout")
def logout(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    create_audit_event(
        db=db,
        event_type="USER_LOGOUT",
        actor_user_id=str(current_user.id),
        metadata={"email": current_user.email},
    )
    return {"message": "Session terminated"}


@router.get("/me")
def get_me(current_user=Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "display_name": current_user.display_name,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat(),
    }
