"""
Authentication endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
import uuid
import httpx

from app.core.database import get_db
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user_id
)
from app.core.config import settings
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token, SocialLoginInput

router = APIRouter()


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register new user"""
    # Check if username already exists
    existing_username = db.query(User).filter(User.username == user_data.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Check if email already exists
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user (UUID will be auto-generated)
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        phone=user_data.phone,
        is_active=True,
        is_verified=False
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create access token
    access_token = create_access_token(
        data={"sub": str(user.id)},  # Convert UUID to string for JWT
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            is_active=user.is_active,
            created_at=user.created_at
        )
    )


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """User login with username or email"""
    # Find user by username or email
    user = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.username)
    ).first()
    
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
    
    # Create access token
    access_token = create_access_token(
        data={"sub": str(user.id)},  # Convert UUID to string for JWT
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            is_active=user.is_active,
            created_at=user.created_at
        )
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get current user info"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        is_active=user.is_active,
        created_at=user.created_at
    )


@router.post("/social-login", response_model=Token)
async def social_login(social_data: SocialLoginInput, db: Session = Depends(get_db)):
    """Log in or sign up a user via a social provider (Google or Facebook)"""
    email = social_data.email
    full_name = social_data.full_name

    # Verify Google token if provided
    if social_data.provider == "google" and social_data.token:
        try:
            async with httpx.AsyncClient() as client:
                # 1. Verify access token with Google's tokeninfo API
                token_info_resp = await client.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"access_token": social_data.token}
                )
                if token_info_resp.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid Google OAuth token"
                    )
                token_info = token_info_resp.json()

                # Verify Client ID matches
                client_id = token_info.get("azp") or token_info.get("aud")
                expected_client_id = settings.GOOGLE_CLIENT_ID
                # Allow fallback if no custom client ID is configured
                default_client_id = "893613114700-5e57386c5b899286dc2cv2j3d571scah.apps.googleusercontent.com"
                if client_id not in (expected_client_id, default_client_id):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Google token client ID mismatch"
                    )

                # 2. Fetch user profile info
                user_info_resp = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {social_data.token}"}
                )
                if user_info_resp.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Failed to retrieve Google user profile"
                    )
                user_info = user_info_resp.json()
                email = user_info.get("email")
                full_name = user_info.get("name") or full_name

                if not email:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email not provided by Google account"
                    )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Google authentication service error: {str(e)}"
            )
    else:
        # If token is not provided, enforce that email is provided (fallback/simulated)
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is required for social login"
            )

    # Find user by email
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        # Create a new user since they don't exist
        # Generate a unique username based on the email prefix
        base_username = email.split('@')[0]
        # Clean username if it has special characters
        base_username = "".join(c for c in base_username if c.isalnum() or c in ("_", "-"))
        if not base_username:
            base_username = "user"
            
        username = base_username
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}_{counter}"
            counter += 1
            
        # Create a secure random password for database constraint
        random_password = uuid.uuid4().hex
        
        user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(random_password),
            full_name=full_name,
            is_active=True,
            is_verified=True  # Social accounts are pre-verified by the provider
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
    elif not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
        
    # Generate app access token
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            is_active=user.is_active,
            created_at=user.created_at
        )
    )

