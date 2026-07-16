from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    email: EmailStr
    phone: Optional[str] = None
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Profile ----------
class ProfileBase(BaseModel):
    name: str
    age: int = Field(ge=18, le=100)
    gender: str
    interested_in: str
    facebook_username: str = Field(min_length=1, description="Required for identity verification")
    county: Optional[str] = None
    bio: Optional[str] = None
    interests: Optional[str] = None
    photo_url: Optional[str] = None


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    interested_in: Optional[str] = None
    facebook_username: Optional[str] = None
    county: Optional[str] = None
    bio: Optional[str] = None
    interests: Optional[str] = None
    photo_url: Optional[str] = None


class ProfileOut(ProfileBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True


# ---------- Swipe / Match ----------
class SwipeRequest(BaseModel):
    swiped_id: int
    direction: str  # "like" or "pass"


class SwipeResult(BaseModel):
    matched: bool
    match_id: Optional[int] = None


class MatchOut(BaseModel):
    id: int
    other_profile: ProfileOut
    match_type: str = "swipe"
    icebreaker: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Random Connect (Ablo-style instant pairing) ----------
class RandomFindResponse(BaseModel):
    status: str  # "waiting" or "matched"
    queue_id: Optional[int] = None
    match_id: Optional[int] = None
    other_profile: Optional[ProfileOut] = None
    icebreaker: Optional[str] = None


class RandomStatusOut(BaseModel):
    status: str  # "waiting" or "matched"
    match_id: Optional[int] = None
    other_profile: Optional[ProfileOut] = None
    icebreaker: Optional[str] = None


class MyStatusOut(BaseModel):
    is_premium: bool
    free_random_remaining: int
    daily_free_random_connects: int


# ---------- Premium (one-time "unlock everything") ----------
class PremiumInitiateRequest(BaseModel):
    phone: str = Field(min_length=9)


class PremiumInitiateResponse(BaseModel):
    payment_id: int
    checkout_request_id: Optional[str] = None
    status: str
    message: str


class PremiumStatusOut(BaseModel):
    status: str
    is_premium: bool


# ---------- Safety: block / report ----------
class ReportRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=100)
    details: Optional[str] = Field(default=None, max_length=1000)


class SimpleOk(BaseModel):
    ok: bool = True


# ---------- Admin panel ----------
class AdminLoginRequest(BaseModel):
    password: str


class AdminToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SettingsUpdate(BaseModel):
    unlock_price_ksh: Optional[str] = None
    premium_price_ksh: Optional[str] = None
    daily_free_random_connects: Optional[str] = None
    daraja_env: Optional[str] = None
    daraja_consumer_key: Optional[str] = None
    daraja_consumer_secret: Optional[str] = None
    daraja_shortcode: Optional[str] = None
    daraja_passkey: Optional[str] = None
    daraja_callback_url: Optional[str] = None
    app_name: Optional[str] = None


class AdminUserOut(BaseModel):
    id: int
    email: str
    phone: Optional[str] = None
    is_banned: bool
    is_premium: bool
    created_at: datetime
    name: Optional[str] = None

    class Config:
        from_attributes = True


class AdminStatsOut(BaseModel):
    total_users: int
    total_matches: int
    total_messages: int
    total_reports: int
    unlocks_completed: int
    revenue_ksh: int
    premium_users: int
    premium_revenue_ksh: int


class AdminReportOut(BaseModel):
    id: int
    reporter_id: int
    reported_id: int
    reason: str
    details: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Contact unlock (M-Pesa paywall) ----------
class UnlockInitiateRequest(BaseModel):
    phone: str = Field(min_length=9, description="M-Pesa number to charge, e.g. 07XXXXXXXX")


class UnlockInitiateResponse(BaseModel):
    payment_id: int
    checkout_request_id: Optional[str] = None
    status: str
    message: str


class UnlockStatusOut(BaseModel):
    status: str
    unlocked: bool


class ContactOut(BaseModel):
    unlocked: bool
    phone: Optional[str] = None
    facebook_username: Optional[str] = None
    price_ksh: Optional[int] = None


# ---------- Messages ----------
class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: int
    match_id: int
    sender_id: int
    content: str
    created_at: datetime

    class Config:
        from_attributes = True
