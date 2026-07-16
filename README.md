# Fiti — Find Someone as Fiti as You 🔥

A full-stack dating app built for Kenya / East Africa: mutual-match swiping,
real-time-ish chat, and a "Fiti Stamp" compatibility reveal when two people
match. Built with a distinct visual identity (bright matatu-graffiti palette,
bold poster type) rather than a templated look.

## Stack

- **Backend:** FastAPI + SQLAlchemy + SQLite (swap to Postgres via `DATABASE_URL`), JWT auth (passlib/bcrypt + python-jose)
- **Frontend:** Plain HTML/CSS/JS (no build step) — easy to host anywhere static

## Features

- Email/password signup & login (JWT)
- Profile creation & editing (name, age, gender, orientation, county, bio, interests, **mandatory Facebook username**)
- Discover deck with swipe (like/pass), drag-to-swipe or buttons
- **Random Connect** — Ablo-style instant pairing: tap one button, get matched with whoever else is online right now (no swiping), plus an auto-generated icebreaker to start the conversation
- Mutual-match detection with an animated "Fiti Stamp" compatibility reveal
- Matches list → 1:1 chat per match (polling-based, 4s refresh)
- **Block & Report** on any match — blocking is instant and mutual
- 18+ / community-guidelines confirmation checkbox at signup (backend also hard-enforces age ≥ 18 on profile creation)
- **Free / Premium tiers**: free accounts get a limited number of Random Connects per day (configurable, default 3); a one-time KSH 50 (configurable) M-Pesa payment unlocks unlimited Random Connects *and* every match's contact info automatically — no more per-match payments
- **Pay-to-unlock contact** (non-premium users) — KSH 50 (configurable) via M-Pesa STK push unlocks a single match's phone number + Facebook username
- **Admin panel** (`frontend/admin.html`) — a single password gets you a no-code dashboard to: set your Daraja (M-Pesa) credentials, change unlock/premium pricing and the daily free-connect limit, view stats/revenue (including premium revenue), ban/unban users, and review reports. Nobody needs to touch the codebase to run the business day-to-day.

## Admin panel

Open `frontend/admin.html` (same hosting as the main frontend, just a
different page — e.g. `https://your-fiti.vercel.app/admin.html`). Log in
with the password you set in `ADMIN_PASSWORD` on the backend (default is
`changeme-admin` — **change this before going live**). From there you can:

- Enter your Safaricom Daraja Consumer Key/Secret, Shortcode, and Passkey
- Set the callback URL (`https://your-backend-url/mpesa/callback`)
- Switch between sandbox (testing) and production (live) M-Pesa
- Change the contact-unlock price
- See total users/matches/revenue
- Ban or unban any user
- Review reports submitted from the app

### Getting real Daraja credentials

You'll need your own Safaricom developer account:
1. Register at [developer.safaricom.co.ke](https://developer.safaricom.co.ke)
2. Create an app to get a sandbox Consumer Key/Secret for testing (works with test phone numbers only)
3. For real payments, apply for a **Lipa Na M-Pesa Online (till/paybill)** production shortcode — this requires business registration with Safaricom and their approval, which is outside anything I can do for you
4. Once approved, switch the admin panel's environment to "production" and enter your live shortcode/passkey

## Run locally

> **If you previously deployed an earlier version of this app**: this update
> added new database columns/tables (Random Connect, Premium). SQLite won't
> auto-migrate an existing `fiti.db` — delete it (or use a fresh Postgres
> database) so the app can recreate the schema on next startup. Any test data
> from before will be lost.

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API will be live at `http://localhost:8000` (interactive docs at `/docs`).
SQLite file `fiti.db` is created automatically on first run.

### Frontend

Just open `frontend/index.html` in a browser, or serve it:

```bash
cd frontend
python3 -m http.server 5500
```

Then visit `http://localhost:5500`. It talks to the backend at
`http://localhost:8000` by default (see the inline `<script>` at the bottom
of `index.html` — change `window.FITI_API_BASE` when you deploy).

## Deploying

- **Backend → Render**: `render.yaml` is included. Push this repo to GitHub,
  connect it in Render, and it'll build/run the `backend/` folder
  automatically. It auto-generates a `SECRET_KEY`; you'll be prompted to set
  `ADMIN_PASSWORD` yourself in the Render dashboard (this is your `/admin`
  login — pick something you don't mind sharing with nobody else). Switch
  `DATABASE_URL` to a managed Postgres instance for real production use
  (SQLite is fine for a demo but doesn't survive redeploys on most hosts).
- **Frontend → Vercel**: `vercel.json` is included, pointing at `frontend/`
  as a static site. After deploying the backend, update
  `window.FITI_API_BASE` in `frontend/index.html` to your live Render URL
  and redeploy the frontend.

## Environment variables (backend)

| Variable       | Purpose                                  | Default (dev only)              |
|----------------|-------------------------------------------|----------------------------------|
| `SECRET_KEY`   | JWT signing secret                        | insecure dev default — **must** change in production |
| `DATABASE_URL` | SQLAlchemy connection string              | `sqlite:///./fiti.db`          |

## What's not included (next steps)

- Real photo upload/storage (currently `photo_url` is just a string field —
  wire up S3/Cloudinary or similar)
- Push notifications for new matches/messages (currently polling)
- Admin moderation dashboard for reviewing reports
- Phone/OTP verification (Daraja or similar, if you want to tie identity to
  M-Pesa-verified phone numbers the way Bit Moja does)
- Rate limiting / abuse prevention on signup and messaging
- Terms of Service & Privacy Policy pages (the signup checkbox references
  "community guidelines" — you'll want real legal copy before launch, ideally
  reviewed by a lawyer familiar with Kenyan data protection law)
