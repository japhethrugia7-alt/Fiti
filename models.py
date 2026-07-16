from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_banned = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)          # one-time KSH 50 "unlock everything"
    free_random_used = Column(Integer, default=0)        # random-connects used today
    free_random_reset_date = Column(String, nullable=True)  # "YYYY-MM-DD", resets the counter
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete")


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)          # man / woman / other
    interested_in = Column(String, nullable=False)    # man / woman / everyone
    county = Column(String, nullable=True)            # e.g. Nairobi, Mombasa, Kisumu
    bio = Column(Text, nullable=True)
    interests = Column(String, nullable=True)          # comma separated
    photo_url = Column(String, nullable=True)
    facebook_username = Column(String, nullable=False)  # mandatory, used for identity verification
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="profile")


class Swipe(Base):
    __tablename__ = "swipes"

    id = Column(Integer, primary_key=True, index=True)
    swiper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    swiped_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    direction = Column(String, nullable=False)  # "like" or "pass"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("swiper_id", "swiped_id", name="uq_swipe_pair"),)


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    user1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user2_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    match_type = Column(String, default="swipe")   # "swipe" or "random"
    icebreaker = Column(String, nullable=True)      # conversation-starter shown to both sides
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship("Message", back_populates="match", cascade="all, delete")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    match = relationship("Match", back_populates="messages")


class Block(Base):
    __tablename__ = "blocks"

    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    blocked_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reported_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Setting(Base):
    """Simple key/value store so the admin panel can change config
    (Daraja credentials, unlock price, etc.) without touching code or
    redeploying."""
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)


class UnlockPayment(Base):
    """Tracks a 'pay 50 KSH to unlock contact info' attempt for a match."""
    __tablename__ = "unlock_payments"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    payer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    phone = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(String, default="pending")  # pending / completed / failed
    checkout_request_id = Column(String, nullable=True, index=True)
    merchant_request_id = Column(String, nullable=True)
    mpesa_receipt = Column(String, nullable=True)
    result_desc = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PremiumPayment(Base):
    """Tracks a 'pay 50 KSH to unlock everything, account-wide' attempt."""
    __tablename__ = "premium_payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    phone = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(String, default="pending")  # pending / completed / failed
    checkout_request_id = Column(String, nullable=True, index=True)
    merchant_request_id = Column(String, nullable=True)
    mpesa_receipt = Column(String, nullable=True)
    result_desc = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RandomQueueEntry(Base):
    """A user waiting to be randomly paired with the next available
    stranger, the way Ablo's globe button worked — no swiping, just
    instant pairing with whoever else is looking right now."""
    __tablename__ = "random_queue"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="waiting")  # waiting / matched
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)
    credited = Column(Boolean, default=False)  # prevents double-counting the daily free-connect quota on repeated polls
    created_at = Column(DateTime(timezone=True), server_default=func.now())
