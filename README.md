# Awaaz Khata

**Bolo, hisaab ho jayega.**

## Problem

Small shopkeepers in India run on udhaar recorded in paper notebooks or memory. Entries get lost, disputes happen, and chasing money feels awkward. They talk all day but should not have to type in English or learn an accounting app. Awaaz Khata is a ledger you talk to, in your own language.

## Product architecture

- **Frontend:** mobile-first HTML, CSS, and JavaScript modules in `frontend/`. The public landing page is `/`; registration and login are `/register` and `/login`; the authenticated voice workbench is `/dashboard`; account controls are at `/settings`.
- **API:** FastAPI routes in `backend/main.py`. Voice uploads still use Gnani Prisma transcription and Timbre speech; parsed transactions remain drafts until explicitly confirmed.
- **Parser:** `backend/parser.py` handles transaction parsing and local voice-query intents. Queries read the signed-in shop’s database and their answers are spoken through Timbre.
- **Data:** SQLite schema and shop-scoped query helpers are in `backend/database.py`. Customers, transactions, and pending confirmations carry a `shop_id`; their reads, writes, edits, and exports always include the authenticated shop ID.
- **Authentication:** PINs are bcrypt hashes. Sessions are expiring HS256 JWTs in HttpOnly, SameSite cookies. Five failed PIN attempts lock that phone for 15 minutes. Configure a stable `JWT_SECRET` (at least 32 random characters) so sessions survive process restarts; set `COOKIE_SECURE=true` when serving over HTTPS.
- **Demo:** “Try demo shop” creates or opens an isolated demo shop with eight customers and 30 mixed Hinglish transactions. Its records reset 24 hours after the previous seed.
- **Exports and reminders:** `/export/ledger` and `/export/customer/{name}` return CSV or PDF. Customer reminders include a prefilled WhatsApp link and, when a shop UPI ID is configured, a UPI payment URI for the exact outstanding amount. PDF export uses the system DejaVu Sans font for multilingual text.
- **PWA:** the manifest and root-scoped service worker cache only the app shell. API responses, ledger data, voice uploads, and exports are never cached; the offline page explains that a connection is needed to access current khata data.

## Setup

1. Install dependencies: `python -m pip install -r requirements.txt`.
2. Copy `.env.example` to `.env`; configure `GNANI_API_KEY_ID`, `GEMINI_API_KEY`, and a stable random `JWT_SECRET`.
3. Start the server: `uvicorn backend.main:app --reload`.
4. Open `http://127.0.0.1:8000/`, create an account, or choose **Try demo shop**.

SQLite data is stored in `ledger.sqlite3` by default. Set `LEDGER_DATABASE_PATH` to use another location.

When upgrading an existing pre-authentication database, the migration preserves its records in a separate locked shop. To make those records accessible to their owner, set `LEGACY_SHOP_PHONE` and a 4–6 digit `LEGACY_SHOP_PIN` before the first upgraded server start. The PIN is immediately bcrypt-hashed. Without both values the records remain isolated as `legacy-unclaimed`; they are never exposed to newly registered shops.

## Routes and behavior

- Public pages: `/`, `/register`, `/login`.
- Public authentication endpoints: `POST /api/register`, `POST /api/login`, and `POST /api/demo-login`.
- Protected account endpoints: `GET /api/me`, `PATCH /api/settings`, `POST /api/logout`, and `DELETE /api/account`.
- Protected voice and ledger endpoints retain their existing paths: `POST /voice`, `POST /confirm`, `GET /ledger`, `GET /customer/{name}`, and `POST /remind/{name}`. `/voice-example` is also protected.
- Supported spoken queries include “Ramesh ka kitna baaki hai?”, “Aaj kitna udhaar diya?”, and “Kisne 30 din se nahi diya?”. Query replies are read-only and scoped to the active shop.
- Customer and whole-ledger exports support `?format=csv` and `?format=pdf`.
- Voice recordings are sent to Gnani for processing and are not stored or logged by this app. Pending transcripts are kept only with an unconfirmed draft and are deleted when it is confirmed or discarded.

## Validation

Run the focused suite with:

```bash
python -m unittest tests.test_parser tests.test_api tests.test_auth tests.test_database
```

The parser corpus is in `tests/parser_cases.json`. Run `python -m tests.test_parser --path fallback` to validate local parsing without a Gemini API call.
