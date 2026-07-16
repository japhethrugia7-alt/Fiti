from typing import List, Optional
from datetime import date

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, not_

import models
import schemas
import settings_store
import mpesa
import icebreakers
from database import engine, get_db, Base
from auth import (
    hash_password, verify_password, create_access_token, get_current_user,
    ADMIN_PASSWORD, create_admin_token, get_current_admin,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Fiti API", description="Backend for Fiti", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your deployed frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Karibu kwa Fiti 🔥 API is running"}


# ---------------- Auth ----------------

@app.post("/auth/register", response_model=schemas.Token, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = models.User(
        email=payload.email,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return schemas.Token(access_token=token)


@app.post("/auth/login", response_model=schemas.Token)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = create_access_token({"sub": str(user.id)})
    return schemas.Token(access_token=token)


# ---------------- Profile ----------------

@app.get("/profiles/me", response_model=schemas.ProfileOut)
def get_my_profile(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(models.Profile).filter(models.Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="No profile yet. Create one first.")
    return profile


@app.post("/profiles/me", response_model=schemas.ProfileOut, status_code=status.HTTP_201_CREATED)
def create_my_profile(
    payload: schemas.ProfileCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(models.Profile).filter(models.Profile.user_id == current_user.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Profile already exists, use PUT to update it")

    profile = models.Profile(user_id=current_user.id, **payload.dict())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@app.put("/profiles/me", response_model=schemas.ProfileOut)
def update_my_profile(
    payload: schemas.ProfileUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(models.Profile).filter(models.Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="No profile yet. Create one first.")

    for field, value in payload.dict(exclude_unset=True).items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return profile


# ---------------- Discover / Swipe ----------------

@app.get("/discover", response_model=List[schemas.ProfileOut])
def discover(
    limit: int = 20,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    my_profile = db.query(models.Profile).filter(models.Profile.user_id == current_user.id).first()
    if not my_profile:
        raise HTTPException(status_code=400, detail="Create your profile before discovering others")

    already_swiped_ids = [
        s.swiped_id for s in db.query(models.Swipe).filter(models.Swipe.swiper_id == current_user.id)
    ]

    blocked_by_me = [b.blocked_id for b in db.query(models.Block).filter(models.Block.blocker_id == current_user.id)]
    blocked_me = [b.blocker_id for b in db.query(models.Block).filter(models.Block.blocked_id == current_user.id)]
    excluded_ids = set(already_swiped_ids) | set(blocked_by_me) | set(blocked_me)

    query = db.query(models.Profile).filter(
        models.Profile.user_id != current_user.id,
        ~models.Profile.user_id.in_(excluded_ids) if excluded_ids else True,
    )

    if my_profile.interested_in in ("man", "woman"):
        query = query.filter(models.Profile.gender == my_profile.interested_in)

    profiles = query.limit(limit).all()
    return profiles


# ---------------- Safety: block & report ----------------
# A "well-behaved" platform needs an easy exit: any match can be blocked or
# reported at any time, and blocking immediately hides both people from
# each other's Discover queue.

@app.post("/users/{user_id}/block", response_model=schemas.SimpleOk)
def block_user(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot block yourself")

    existing = db.query(models.Block).filter(
        models.Block.blocker_id == current_user.id, models.Block.blocked_id == user_id
    ).first()
    if not existing:
        db.add(models.Block(blocker_id=current_user.id, blocked_id=user_id))
        db.commit()
    return schemas.SimpleOk()


@app.post("/users/{user_id}/report", response_model=schemas.SimpleOk)
def report_user(
    user_id: int,
    payload: schemas.ReportRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot report yourself")

    db.add(models.Report(
        reporter_id=current_user.id,
        reported_id=user_id,
        reason=payload.reason,
        details=payload.details,
    ))
    # Reporting also blocks the user automatically, so the reporter is never
    # forced to keep seeing someone they've flagged.
    already_blocked = db.query(models.Block).filter(
        models.Block.blocker_id == current_user.id, models.Block.blocked_id == user_id
    ).first()
    if not already_blocked:
        db.add(models.Block(blocker_id=current_user.id, blocked_id=user_id))
    db.commit()
    return schemas.SimpleOk()


@app.post("/swipe", response_model=schemas.SwipeResult)
def swipe(
    payload: schemas.SwipeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.direction not in ("like", "pass"):
        raise HTTPException(status_code=400, detail="direction must be 'like' or 'pass'")

    if payload.swiped_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot swipe on yourself")

    existing = db.query(models.Swipe).filter(
        models.Swipe.swiper_id == current_user.id,
        models.Swipe.swiped_id == payload.swiped_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already swiped on this profile")

    new_swipe = models.Swipe(
        swiper_id=current_user.id,
        swiped_id=payload.swiped_id,
        direction=payload.direction,
    )
    db.add(new_swipe)
    db.commit()

    if payload.direction == "like":
        reciprocal = db.query(models.Swipe).filter(
            models.Swipe.swiper_id == payload.swiped_id,
            models.Swipe.swiped_id == current_user.id,
            models.Swipe.direction == "like",
        ).first()
        if reciprocal:
            match = models.Match(user1_id=current_user.id, user2_id=payload.swiped_id)
            db.add(match)
            db.commit()
            db.refresh(match)
            return schemas.SwipeResult(matched=True, match_id=match.id)

    return schemas.SwipeResult(matched=False)


# ---------------- Matches & Messages ----------------

@app.get("/matches", response_model=List[schemas.MatchOut])
def list_matches(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    matches = db.query(models.Match).filter(
        or_(models.Match.user1_id == current_user.id, models.Match.user2_id == current_user.id)
    ).all()

    blocked_by_me = {b.blocked_id for b in db.query(models.Block).filter(models.Block.blocker_id == current_user.id)}
    blocked_me = {b.blocker_id for b in db.query(models.Block).filter(models.Block.blocked_id == current_user.id)}
    hidden_ids = blocked_by_me | blocked_me

    result = []
    for m in matches:
        other_id = m.user2_id if m.user1_id == current_user.id else m.user1_id
        if other_id in hidden_ids:
            continue
        other_profile = db.query(models.Profile).filter(models.Profile.user_id == other_id).first()
        if other_profile:
            result.append(schemas.MatchOut(
                id=m.id, other_profile=other_profile, match_type=m.match_type,
                icebreaker=m.icebreaker, created_at=m.created_at,
            ))
    return result


def _get_match_or_403(match_id: int, current_user: models.User, db: Session) -> models.Match:
    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if current_user.id not in (match.user1_id, match.user2_id):
        raise HTTPException(status_code=403, detail="Not part of this match")
    return match


@app.get("/matches/{match_id}/messages", response_model=List[schemas.MessageOut])
def get_messages(
    match_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_match_or_403(match_id, current_user, db)
    messages = db.query(models.Message).filter(models.Message.match_id == match_id).order_by(
        models.Message.created_at.asc()
    ).all()
    return messages


@app.post("/matches/{match_id}/messages", response_model=schemas.MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    match_id: int,
    payload: schemas.MessageCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_match_or_403(match_id, current_user, db)
    message = models.Message(match_id=match_id, sender_id=current_user.id, content=payload.content)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


# ================================================================
# RANDOM CONNECT — instant stranger pairing, Ablo-style: tap one
# button, get paired with whoever else is looking right now (no
# swiping, no profile browsing), with an icebreaker to start things
# off. Free users get a limited number of these per day; premium
# users get unlimited.
# ================================================================

def _today_str() -> str:
    return date.today().isoformat()


def _ensure_daily_reset(user: models.User, db: Session) -> None:
    today = _today_str()
    if user.free_random_reset_date != today:
        user.free_random_reset_date = today
        user.free_random_used = 0
        db.commit()


def _free_random_remaining(db: Session, user: models.User) -> int:
    _ensure_daily_reset(user, db)
    limit = int(settings_store.get_setting(db, "daily_free_random_connects") or 3)
    return max(0, limit - user.free_random_used)


@app.get("/me/status", response_model=schemas.MyStatusOut)
def my_status(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    limit = int(settings_store.get_setting(db, "daily_free_random_connects") or 3)
    remaining = limit if current_user.is_premium else _free_random_remaining(db, current_user)
    return schemas.MyStatusOut(
        is_premium=current_user.is_premium,
        free_random_remaining=remaining,
        daily_free_random_connects=limit,
    )


def _profile_for(db: Session, user_id: int) -> Optional[models.Profile]:
    return db.query(models.Profile).filter(models.Profile.user_id == user_id).first()


def _other_user_id(match: models.Match, current_user_id: int) -> int:
    return match.user2_id if match.user1_id == current_user_id else match.user1_id


@app.post("/random/find", response_model=schemas.RandomFindResponse)
def random_find(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    my_profile = db.query(models.Profile).filter(models.Profile.user_id == current_user.id).first()
    if not my_profile:
        raise HTTPException(status_code=400, detail="Create your profile before using Random Connect")

    if not current_user.is_premium and _free_random_remaining(db, current_user) <= 0:
        raise HTTPException(
            status_code=402,
            detail="You've used today's free random connects. Upgrade to Premium for unlimited.",
        )

    # Clear out any stale queue entry of my own before looking for someone else.
    db.query(models.RandomQueueEntry).filter(
        models.RandomQueueEntry.user_id == current_user.id,
        models.RandomQueueEntry.status == "waiting",
    ).delete()
    db.commit()

    # Look for someone else already waiting (ignore blocked users in either direction).
    blocked_by_me = [b.blocked_id for b in db.query(models.Block).filter(models.Block.blocker_id == current_user.id)]
    blocked_me = [b.blocker_id for b in db.query(models.Block).filter(models.Block.blocked_id == current_user.id)]
    excluded = set(blocked_by_me) | set(blocked_me) | {current_user.id}

    waiting_entry = db.query(models.RandomQueueEntry).filter(
        models.RandomQueueEntry.status == "waiting",
        ~models.RandomQueueEntry.user_id.in_(excluded),
    ).order_by(models.RandomQueueEntry.created_at.asc()).first()

    if waiting_entry:
        icebreaker = icebreakers.random_icebreaker()
        match = models.Match(
            user1_id=current_user.id, user2_id=waiting_entry.user_id,
            match_type="random", icebreaker=icebreaker,
        )
        db.add(match)
        db.commit()
        db.refresh(match)

        waiting_entry.status = "matched"
        waiting_entry.match_id = match.id
        db.commit()

        if not current_user.is_premium:
            current_user.free_random_used += 1
            db.commit()

        other_profile = _profile_for(db, waiting_entry.user_id)
        return schemas.RandomFindResponse(
            status="matched", match_id=match.id,
            other_profile=other_profile, icebreaker=icebreaker,
        )

    # Nobody's waiting — join the queue myself.
    entry = models.RandomQueueEntry(user_id=current_user.id, status="waiting")
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return schemas.RandomFindResponse(status="waiting", queue_id=entry.id)


@app.get("/random/status/{queue_id}", response_model=schemas.RandomStatusOut)
def random_status(
    queue_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = db.query(models.RandomQueueEntry).filter(models.RandomQueueEntry.id == queue_id).first()
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    if entry.status != "matched" or not entry.match_id:
        return schemas.RandomStatusOut(status="waiting")

    match = db.query(models.Match).filter(models.Match.id == entry.match_id).first()
    other_id = _other_user_id(match, current_user.id)

    if not current_user.is_premium and not entry.credited:
        current_user.free_random_used += 1
        entry.credited = True
        db.commit()

    return schemas.RandomStatusOut(
        status="matched", match_id=match.id,
        other_profile=_profile_for(db, other_id), icebreaker=match.icebreaker,
    )


# ================================================================
# CONTACT UNLOCK — pay KSH 50 (configurable) via M-Pesa to reveal a
# match's phone number and Facebook username.
# ================================================================

def _is_unlocked(db: Session, match_id: int, payer_id: int) -> bool:
    user = db.query(models.User).filter(models.User.id == payer_id).first()
    if user and user.is_premium:
        return True  # premium unlocks every match's contact automatically
    return db.query(models.UnlockPayment).filter(
        models.UnlockPayment.match_id == match_id,
        models.UnlockPayment.payer_id == payer_id,
        models.UnlockPayment.status == "completed",
    ).first() is not None


@app.get("/matches/{match_id}/contact", response_model=schemas.ContactOut)
def get_contact(
    match_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    match = _get_match_or_403(match_id, current_user, db)
    price = int(settings_store.get_setting(db, "unlock_price_ksh") or 50)

    if not _is_unlocked(db, match_id, current_user.id):
        return schemas.ContactOut(unlocked=False, price_ksh=price)

    other_id = _other_user_id(match, current_user.id)
    other_user = db.query(models.User).filter(models.User.id == other_id).first()
    other_profile = db.query(models.Profile).filter(models.Profile.user_id == other_id).first()
    return schemas.ContactOut(
        unlocked=True,
        phone=other_user.phone if other_user else None,
        facebook_username=other_profile.facebook_username if other_profile else None,
    )


@app.post("/matches/{match_id}/unlock/initiate", response_model=schemas.UnlockInitiateResponse)
def initiate_unlock(
    match_id: int,
    payload: schemas.UnlockInitiateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_match_or_403(match_id, current_user, db)

    if _is_unlocked(db, match_id, current_user.id):
        return schemas.UnlockInitiateResponse(payment_id=0, status="completed", message="Already unlocked")

    price = int(settings_store.get_setting(db, "unlock_price_ksh") or 50)

    payment = models.UnlockPayment(
        match_id=match_id, payer_id=current_user.id, phone=payload.phone,
        amount=price, status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    try:
        result = mpesa.initiate_stk_push(
            db, payload.phone, price,
            account_ref=f"FITI-{match_id}",
            description="Unlock Fiti contact",
        )
    except Exception as e:
        payment.status = "failed"
        payment.result_desc = str(e)
        db.commit()
        raise HTTPException(status_code=502, detail=str(e))

    payment.checkout_request_id = result.get("CheckoutRequestID")
    payment.merchant_request_id = result.get("MerchantRequestID")
    db.commit()

    return schemas.UnlockInitiateResponse(
        payment_id=payment.id,
        checkout_request_id=payment.checkout_request_id,
        status="pending",
        message="Check your phone and enter your M-Pesa PIN to complete payment.",
    )


@app.get("/unlock-payments/{payment_id}/status", response_model=schemas.UnlockStatusOut)
def unlock_status(
    payment_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payment = db.query(models.UnlockPayment).filter(models.UnlockPayment.id == payment_id).first()
    if not payment or payment.payer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    return schemas.UnlockStatusOut(status=payment.status, unlocked=payment.status == "completed")


# ================================================================
# PREMIUM — one-time KSH 50 (configurable) to unlock everything
# account-wide: unlimited Random Connects + every match's contact
# info revealed automatically, no more per-match payments.
# ================================================================

@app.post("/premium/initiate", response_model=schemas.PremiumInitiateResponse)
def initiate_premium(
    payload: schemas.PremiumInitiateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.is_premium:
        return schemas.PremiumInitiateResponse(payment_id=0, status="completed", message="Already premium")

    price = int(settings_store.get_setting(db, "premium_price_ksh") or 50)

    payment = models.PremiumPayment(
        user_id=current_user.id, phone=payload.phone, amount=price, status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    try:
        result = mpesa.initiate_stk_push(
            db, payload.phone, price,
            account_ref=f"FITI-PREMIUM-{current_user.id}",
            description="Fiti Premium — unlock everything",
        )
    except Exception as e:
        payment.status = "failed"
        payment.result_desc = str(e)
        db.commit()
        raise HTTPException(status_code=502, detail=str(e))

    payment.checkout_request_id = result.get("CheckoutRequestID")
    payment.merchant_request_id = result.get("MerchantRequestID")
    db.commit()

    return schemas.PremiumInitiateResponse(
        payment_id=payment.id,
        checkout_request_id=payment.checkout_request_id,
        status="pending",
        message="Check your phone and enter your M-Pesa PIN to complete payment.",
    )


@app.get("/premium/status/{payment_id}", response_model=schemas.PremiumStatusOut)
def premium_status(
    payment_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payment = db.query(models.PremiumPayment).filter(models.PremiumPayment.id == payment_id).first()
    if not payment or payment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    return schemas.PremiumStatusOut(status=payment.status, is_premium=current_user.is_premium)


@app.post("/mpesa/callback")
async def mpesa_callback(request: Request, db: Session = Depends(get_db)):
    """Safaricom calls this URL directly (no user auth) with the payment
    result. Configure this exact URL — https://<your-backend>/mpesa/callback
    — as the Daraja callback in /admin. Routes to whichever payment table
    (per-match unlock or account-wide premium) the CheckoutRequestID belongs to."""
    body = await request.json()
    stk = body.get("Body", {}).get("stkCallback", {})
    checkout_id = stk.get("CheckoutRequestID")
    result_code = stk.get("ResultCode")
    result_desc = stk.get("ResultDesc")

    def _extract_receipt():
        items = stk.get("CallbackMetadata", {}).get("Item", [])
        for item in items:
            if item.get("Name") == "MpesaReceiptNumber":
                return item.get("Value")
        return None

    unlock_payment = db.query(models.UnlockPayment).filter(
        models.UnlockPayment.checkout_request_id == checkout_id
    ).first()
    if unlock_payment:
        if result_code == 0:
            unlock_payment.status = "completed"
            unlock_payment.mpesa_receipt = _extract_receipt()
        else:
            unlock_payment.status = "failed"
        unlock_payment.result_desc = result_desc
        db.commit()
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    premium_payment = db.query(models.PremiumPayment).filter(
        models.PremiumPayment.checkout_request_id == checkout_id
    ).first()
    if premium_payment:
        if result_code == 0:
            premium_payment.status = "completed"
            premium_payment.mpesa_receipt = _extract_receipt()
            user = db.query(models.User).filter(models.User.id == premium_payment.user_id).first()
            if user:
                user.is_premium = True
        else:
            premium_payment.status = "failed"
        premium_payment.result_desc = result_desc
        db.commit()
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    return {"ResultCode": 0, "ResultDesc": "Accepted"}


# ================================================================
# ADMIN PANEL — one password, full non-technical control:
# Daraja credentials, unlock pricing, user list/bans, reports.
# ================================================================

@app.post("/admin/login", response_model=schemas.AdminToken)
def admin_login(payload: schemas.AdminLoginRequest):
    if payload.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect admin password")
    return schemas.AdminToken(access_token=create_admin_token())


@app.get("/admin/settings")
def admin_get_settings(_: bool = Depends(get_current_admin), db: Session = Depends(get_db)):
    return settings_store.masked_settings(db)


@app.put("/admin/settings")
def admin_update_settings(
    payload: schemas.SettingsUpdate,
    _: bool = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    for field, value in payload.dict(exclude_unset=True).items():
        if value is not None and value != "":
            settings_store.set_setting(db, field, value)
    return settings_store.masked_settings(db)


@app.get("/admin/stats", response_model=schemas.AdminStatsOut)
def admin_stats(_: bool = Depends(get_current_admin), db: Session = Depends(get_db)):
    completed = db.query(models.UnlockPayment).filter(models.UnlockPayment.status == "completed").all()
    premium_completed = db.query(models.PremiumPayment).filter(models.PremiumPayment.status == "completed").all()
    return schemas.AdminStatsOut(
        total_users=db.query(models.User).count(),
        total_matches=db.query(models.Match).count(),
        total_messages=db.query(models.Message).count(),
        total_reports=db.query(models.Report).count(),
        unlocks_completed=len(completed),
        revenue_ksh=sum(p.amount for p in completed),
        premium_users=db.query(models.User).filter(models.User.is_premium == True).count(),
        premium_revenue_ksh=sum(p.amount for p in premium_completed),
    )


@app.get("/admin/users", response_model=List[schemas.AdminUserOut])
def admin_list_users(_: bool = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.created_at.desc()).limit(200).all()
    out = []
    for u in users:
        profile = db.query(models.Profile).filter(models.Profile.user_id == u.id).first()
        out.append(schemas.AdminUserOut(
            id=u.id, email=u.email, phone=u.phone, is_banned=u.is_banned,
            is_premium=u.is_premium, created_at=u.created_at, name=profile.name if profile else None,
        ))
    return out


@app.post("/admin/users/{user_id}/ban", response_model=schemas.SimpleOk)
def admin_ban_user(user_id: int, _: bool = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_banned = True
    db.commit()
    return schemas.SimpleOk()


@app.post("/admin/users/{user_id}/unban", response_model=schemas.SimpleOk)
def admin_unban_user(user_id: int, _: bool = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_banned = False
    db.commit()
    return schemas.SimpleOk()


@app.get("/admin/reports", response_model=List[schemas.AdminReportOut])
def admin_list_reports(_: bool = Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(models.Report).order_by(models.Report.created_at.desc()).limit(200).all()


@app.get("/settings/public")
def public_settings(db: Session = Depends(get_db)):
    """Non-sensitive settings the frontend needs, like current pricing."""
    return {
        "unlock_price_ksh": int(settings_store.get_setting(db, "unlock_price_ksh") or 50),
        "premium_price_ksh": int(settings_store.get_setting(db, "premium_price_ksh") or 50),
        "daily_free_random_connects": int(settings_store.get_setting(db, "daily_free_random_connects") or 3),
        "app_name": settings_store.get_setting(db, "app_name") or "Fiti",
    }
