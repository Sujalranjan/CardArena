"""Authentication and user management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.auth import create_access_token, get_current_user
from app.database.session import get_db
from app.models.models import User
from app.schemas.schemas import TokenResponse, UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login_or_register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """Simple login/register by username for Phase 1 user identity foundation."""
    username = user_in.username.strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")

    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            username=username,
            display_name=user_in.display_name.strip() or username,
            avatar=user_in.avatar or "default",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        if user_in.display_name and user.display_name != user_in.display_name:
            user.display_name = user_in.display_name
            await db.commit()
            await db.refresh(user)

    token = create_access_token({"sub": user.id, "username": user.username})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)
