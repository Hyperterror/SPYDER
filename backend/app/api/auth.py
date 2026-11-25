from datetime import datetime, timedelta, timezone
import hmac
import secrets
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    bearer_scheme,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    verify_password,
)
from app.models.auth import UserSession
from app.models.user import User
from app.services.audit_svc import create_audit_event

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "spyder_refresh_token"
CSRF_COOKIE_NAME = "spyder_csrf_token"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


def _set_auth_cookies(response: Response, refresh_token: str) -> str:
    csrf_token = secrets.token_urlsafe(32)
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=max_age,
        path="/api/v1/auth",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=max_age,
        path="/",
    )
    return csrf_token


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/v1/auth")
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")


def _verify_csrf_if_cookie_auth(request: Request) -> None:
    """When refresh token arrives via cookie (no JSON body), require double-submit CSRF token."""
    cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)
    header_csrf = request.headers.get("X-CSRF-Token")
    if not cookie_csrf or not header_csrf or not hmac.compare_digest(cookie_csrf, header_csrf):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    request: Request = None,
):
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user or not verify_password(body.password, user.password_hash):
        create_audit_event(
            db=db,
            event_type="USER_LOGIN_FAILED",
            metadata={"email": body.email},
            ip_address=str(request.client.host) if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_id = uuid.uuid4()
    jti = uuid.uuid4().hex
    family_id = uuid.uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    session = UserSession(
        id=session_id,
        user_id=user.id,
        refresh_token_jti=jti,
        token_family_id=family_id,
        expires_at=expires_at,
        ip_address=str(request.client.host) if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(session)
    db.commit()

    access = create_access_token(str(user.id), user.role, session_id=str(session_id))
    refresh = create_refresh_token(str(user.id), session_id=str(session_id), jti=jti, family_id=family_id)
    _set_auth_cookies(response, refresh)

    create_audit_event(
        db=db,
        event_type="USER_LOGIN",
        actor_user_id=str(user.id),
        metadata={"email": user.email, "role": user.role, "session_id": str(session_id)},
        ip_address=str(request.client.host) if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )

    return TokenResponse(
        access_token=access,
        refresh_token=refresh if settings.ALLOW_BODY_REFRESH else None,
        user={
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "organization_id": str(user.organization_id) if user.organization_id else None,
        },
    )


@router.post("/refresh")
def refresh_token(
    request: Request,
    response: Response,
    body: Optional[RefreshRequest] = None,
    db: Session = Depends(get_db),
):
    cookie_token = request.cookies.get(REFRESH_COOKIE_NAME)
    body_token = body.refresh_token if (body and settings.ALLOW_BODY_REFRESH) else None

    if cookie_token and not body_token:
        _verify_csrf_if_cookie_auth(request)
        raw_refresh = cookie_token
    elif body_token:
        raw_refresh = body_token
    elif cookie_token:
        _verify_csrf_if_cookie_auth(request)
        raw_refresh = cookie_token
    else:
        raise HTTPException(status_code=401, detail="Refresh token required")

    payload = decode_token(raw_refresh)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    jti = payload.get("jti")
    sub = payload.get("sub")
    if not jti or not sub:
        raise HTTPException(status_code=401, detail="Malformed refresh token")

    session = db.query(UserSession).filter(UserSession.refresh_token_jti == jti).first()
    if not session:
        raise HTTPException(status_code=401, detail="Session not found")

    now = datetime.now(timezone.utc)

    # Reuse detection: if an already-revoked/rotated refresh token is presented,
    # revoke the entire token family immediately!
    if session.revoked_at is not None:
        db.query(UserSession).filter(
            UserSession.token_family_id == session.token_family_id,
            UserSession.revoked_at.is_(None),
        ).update(
            {"revoked_at": now, "revocation_reason": "REFRESH_TOKEN_REUSE_DETECTED"},
            synchronize_session=False,
        )
        db.commit()
        create_audit_event(
            db=db,
            event_type="SECURITY_TOKEN_REUSE_DETECTED",
            actor_user_id=str(session.user_id),
            metadata={"token_family_id": session.token_family_id, "jti": jti},
            ip_address=str(request.client.host) if request and request.client else None,
        )
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh token reuse detected; session family revoked")

    exp = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
    if exp <= now:
        session.revoked_at = now
        session.revocation_reason = "EXPIRED"
        db.commit()
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.query(User).filter(User.id == session.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Rotate refresh token within the same token_family_id
    new_session_id = uuid.uuid4()
    new_jti = uuid.uuid4().hex
    session.revoked_at = now
    session.revocation_reason = "ROTATED"
    session.replaced_by_jti = new_jti

    new_session = UserSession(
        id=new_session_id,
        user_id=user.id,
        refresh_token_jti=new_jti,
        token_family_id=session.token_family_id,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=str(request.client.host) if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(new_session)
    db.commit()

    new_access = create_access_token(str(user.id), user.role, session_id=str(new_session_id))
    new_refresh = create_refresh_token(
        str(user.id), session_id=str(new_session_id), jti=new_jti, family_id=session.token_family_id
    )
    _set_auth_cookies(response, new_refresh)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh if settings.ALLOW_BODY_REFRESH else None,
        "token_type": "bearer",
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user=Depends(get_current_user),
    credentials=Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    revoked_sessions = 0

    # Revoke session referenced by access token's sid claim
    if credentials and credentials.credentials:
        try:
            payload = decode_token(credentials.credentials)
            sid = payload.get("sid")
            if sid:
                sess = db.query(UserSession).filter(
                    UserSession.id == uuid.UUID(str(sid)),
                    UserSession.user_id == current_user.id,
                    UserSession.revoked_at.is_(None),
                ).first()
                if sess:
                    sess.revoked_at = now
                    sess.revocation_reason = "LOGOUT"
                    revoked_sessions += 1
        except Exception:
            pass

    # Also revoke session referenced by refresh cookie if present
    cookie_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if cookie_token:
        try:
            r_payload = decode_token(cookie_token)
            r_jti = r_payload.get("jti")
            if r_jti:
                sess = db.query(UserSession).filter(
                    UserSession.refresh_token_jti == r_jti,
                    UserSession.user_id == current_user.id,
                    UserSession.revoked_at.is_(None),
                ).first()
                if sess:
                    sess.revoked_at = now
                    sess.revocation_reason = "LOGOUT"
                    revoked_sessions += 1
        except Exception:
            pass

    db.commit()
    _clear_auth_cookies(response)

    create_audit_event(
        db=db,
        event_type="USER_LOGOUT",
        actor_user_id=str(current_user.id),
        metadata={"email": current_user.email, "revoked_sessions": revoked_sessions},
        ip_address=str(request.client.host) if request and request.client else None,
    )
    return {"message": "Session terminated", "revoked_sessions": revoked_sessions}


@router.get("/me")
def get_me(current_user=Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "display_name": current_user.display_name,
        "role": current_user.role,
        "organization_id": str(current_user.organization_id) if current_user.organization_id else None,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat(),
    }
