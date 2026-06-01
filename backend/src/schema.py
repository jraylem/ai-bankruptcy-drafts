from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional

# Authentication schemas
class UserBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def title_case_name(cls, v):
        if v is None:
            return v
        return v.strip().title()

class UserCreate(UserBase):
    password: str
    firm_name: str  # required — every registration creates a firm

class RegisterResponse(BaseModel):
    """Returned by POST /api/auth/register — no JWT yet, verification required."""
    message: str
    user_id: str

class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class UserResponse(UserBase):
    id: str
    created_at: datetime
    is_active: bool
    is_accepted: bool = False
    email_verified: bool = False
    # Paywall / RBAC fields — null now, populated once firm accounts are live
    firm_id: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[list] = None
    onboarding_status: Optional[str] = None

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class LoginResponse(BaseModel):
    """Response for /auth/login and /auth/refresh.

    Returns the access token in the body for backward compat with the existing
    Bearer-based frontend, plus the full user object so the FE can hydrate
    session state without a second /auth/me call.
    """
    access_token: str
    token_type: str
    user: UserResponse

class TokenData(BaseModel):
    user_id: Optional[str] = None

# Session schemas
class SessionResponse(BaseModel):
    id: str
    user_id: Optional[str]
    created_at: datetime
    thread_id: Optional[str] = None
    
    class Config:
        from_attributes = True

# Chat schemas
class ChatMessage(BaseModel):
    message: str
    session_id: str
    thread_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    thread_id: str

class ChatThreadResponse(BaseModel):
    id: str
    session_id: str
    title: Optional[str]
    summary: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class ChatMessageResponse(BaseModel):
    id: str
    thread_id: str
    role: str
    content: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class ThreadMetadataUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None

# PDF schemas
class PDFUploadResponse(BaseModel):
    message: str
    filename: str
    file_path: str
    size: int
    available_for_review: bool

# Review schemas
class ReviewResultsResponse(BaseModel):
    id: str
    session_id: str
    pdf_path: str
    review_data: str
    created_at: datetime
    
    class Config:
        from_attributes = True
