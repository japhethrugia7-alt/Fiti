import base64
import datetime
import requests
from sqlalchemy.orm import Session

import settings_store

SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
PRODUCTION_BASE = "https://api.safaricom.co.ke"


def _base_url(db: Session) -> str:
    env = settings_store.get_setting(db, "daraja_env")
    return PRODUCTION_BASE if env == "production" else SANDBOX_BASE


def _get_access_token(db: Session) -> str:
    key = settings_store.get_setting(db, "daraja_consumer_key")
    secret = settings_store.get_setting(db, "daraja_consumer_secret")
    if not key or not secret:
        raise RuntimeError(
            "M-Pesa isn't configured yet. Go to /admin and enter your Daraja "
            "Consumer Key and Secret first."
        )

    url = f"{_base_url(db)}/oauth/v1/generate?grant_type=client_credentials"
    resp = requests.get(url, auth=(key, secret), timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _normalize_phone(phone: str) -> str:
    """Convert 07XXXXXXXX / +2547XXXXXXXX / 2547XXXXXXXX into 2547XXXXXXXX."""
    p = phone.strip().replace(" ", "").replace("-", "")
    if p.startswith("+"):
        p = p[1:]
    if p.startswith("0"):
        p = "254" + p[1:]
    if p.startswith("7") or p.startswith("1"):
        p = "254" + p
    return p


def initiate_stk_push(db: Session, phone: str, amount: int, account_ref: str, description: str) -> dict:
    """Kicks off an STK push (the customer gets a PIN prompt on their phone).
    Returns Safaricom's response including CheckoutRequestID, which we store
    and later match against the callback."""
    shortcode = settings_store.get_setting(db, "daraja_shortcode")
    passkey = settings_store.get_setting(db, "daraja_passkey")
    callback_url = settings_store.get_setting(db, "daraja_callback_url")

    if not shortcode or not passkey:
        raise RuntimeError(
            "M-Pesa isn't fully configured yet. Go to /admin and enter your "
            "Shortcode and Passkey first."
        )
    if not callback_url:
        raise RuntimeError(
            "Set your Daraja callback URL in /admin first (your live backend "
            "URL + /mpesa/callback)."
        )

    token = _get_access_token(db)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": _normalize_phone(phone),
        "PartyB": shortcode,
        "PhoneNumber": _normalize_phone(phone),
        "CallBackURL": callback_url,
        "AccountReference": account_ref,
        "TransactionDesc": description,
    }
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(
        f"{_base_url(db)}/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers=headers,
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()
