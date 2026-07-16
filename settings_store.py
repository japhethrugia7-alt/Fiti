from sqlalchemy.orm import Session
import models

# Defaults used until the admin sets real values via the admin panel.
DEFAULTS = {
    "unlock_price_ksh": "50",
    "premium_price_ksh": "50",
    "daily_free_random_connects": "3",
    "daraja_env": "sandbox",           # "sandbox" or "production"
    "daraja_consumer_key": "",
    "daraja_consumer_secret": "",
    "daraja_shortcode": "",
    "daraja_passkey": "",
    "daraja_callback_url": "",         # your public backend URL + /mpesa/callback
    "app_name": "Fiti",
}

# Keys whose values should never be sent back to the frontend in full.
SECRET_KEYS = {"daraja_consumer_secret", "daraja_passkey"}


def get_setting(db: Session, key: str) -> str:
    row = db.query(models.Setting).filter(models.Setting.key == key).first()
    if row and row.value is not None:
        return row.value
    return DEFAULTS.get(key, "")


def get_all_settings(db: Session) -> dict:
    return {key: get_setting(db, key) for key in DEFAULTS}


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(models.Setting).filter(models.Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(models.Setting(key=key, value=value))
    db.commit()


def masked_settings(db: Session) -> dict:
    """Settings safe to show in the admin UI after they've been saved
    (secrets are masked, not echoed back in plaintext)."""
    out = {}
    for key in DEFAULTS:
        val = get_setting(db, key)
        if key in SECRET_KEYS and val:
            out[key] = "•" * 8 + val[-4:] if len(val) > 4 else "••••"
        else:
            out[key] = val
    return out
