import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import EmailVerificationToken, PasswordResetToken, RefreshToken, User
from app.rate_limit import rate_limit_login
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.security import create_access_token, generate_opaque_token, hash_opaque_token, hash_password, verify_password

logger = logging.getLogger("aiflow.auth")
router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _try_send_verification_email(user_email: str, token: str) -> None:
    """Try Celery first; fall back to direct call if worker unavailable."""
    try:
        from app.tasks.email_tasks import send_verification_email_task
        send_verification_email_task.delay(user_email, token)
    except Exception:
        try:
            from app.services.email import send_verification_email
            send_verification_email(user_email, token)
        except Exception as e:
            logger.warning("Could not send verification email: %s", e)


def _try_send_password_reset_email(user_email: str, token: str) -> None:
    """Try Celery first; fall back to direct call if worker unavailable."""
    try:
        from app.tasks.email_tasks import send_password_reset_email_task
        send_password_reset_email_task.delay(user_email, token)
    except Exception:
        try:
            from app.services.email import send_password_reset_email
            send_password_reset_email(user_email, token)
        except Exception as e:
            logger.warning("Could not send password reset email: %s", e)


async def _issue_tokens(db: AsyncSession, user: User) -> TokenResponse:
    access_token = create_access_token(user.id)
    plaintext_refresh, hashed_refresh = generate_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            hashed_token=hashed_refresh,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    await db.commit()
    return TokenResponse(access_token=access_token, refresh_token=plaintext_refresh)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserResponse:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(email=body.email, hashed_password=hash_password(body.password), full_name=body.full_name)
    db.add(user)
    await db.flush()

    plaintext, hashed = generate_opaque_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            hashed_token=hashed,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
        )
    )
    await db.commit()

    _try_send_verification_email(user.email, plaintext)
    return UserResponse.model_validate({**user.__dict__, "id": str(user.id)})


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit_login)])
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")
    return await _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    hashed = hash_opaque_token(body.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.hashed_token == hashed))
    token_row = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not token_row or token_row.revoked_at or token_row.expires_at < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    token_row.revoked_at = now  # rotate: this refresh token is single-use
    user = await db.get(User, token_row.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    # Issue new tokens in the same transaction — revoke old + create new atomically
    access_token = create_access_token(user.id)
    plaintext_refresh, hashed_refresh = generate_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            hashed_token=hashed_refresh,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    await db.commit()
    return TokenResponse(access_token=access_token, refresh_token=plaintext_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> None:
    hashed = hash_opaque_token(body.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.hashed_token == hashed))
    token_row = result.scalar_one_or_none()
    if token_row:
        token_row.revoked_at = datetime.now(timezone.utc)
        await db.commit()


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)) -> None:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user:  # always return 204 either way — don't leak whether an email is registered
        plaintext, hashed = generate_opaque_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                hashed_token=hashed,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
            )
        )
        await db.commit()
        _try_send_password_reset_email(user.email, plaintext)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> None:
    hashed = hash_opaque_token(body.token)
    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.hashed_token == hashed))
    token_row = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not token_row or token_row.used_at or token_row.expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

    user = await db.get(User, token_row.user_id)
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

    user.hashed_password = hash_password(body.new_password)
    token_row.used_at = now
    await db.execute(
        RefreshToken.__table__.update().where(RefreshToken.user_id == user.id).values(revoked_at=now)
    )
    await db.commit()


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> None:
    hashed = hash_opaque_token(body.token)
    result = await db.execute(select(EmailVerificationToken).where(EmailVerificationToken.hashed_token == hashed))
    token_row = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not token_row or token_row.used_at or token_row.expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired verification token")

    user = await db.get(User, token_row.user_id)
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired verification token")

    user.is_email_verified = True
    token_row.used_at = now
    await db.commit()


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate({**current_user.__dict__, "id": str(current_user.id)})
