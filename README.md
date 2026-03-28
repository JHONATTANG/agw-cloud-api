# AGW Cloud API — VitalCrop

> **VitalCrop AGW Cloud API** — FastAPI REST backend for IoT fleet management  
> Python 3.11 · FastAPI 0.110 · asyncpg · SQLAlchemy async · JWT · Docker

---

## Architecture

```
Dashboard (Next.js) ─── REST/JWT ──► Cloud API (FastAPI)
Edge Gateway (RPi)  ─── REST/Token ─► Cloud API (FastAPI)
                                          │
                                     Supabase (PostgreSQL)
```

---

## Quick Start

### 1. Clone & configure

```bash
cp .env.example .env
# Edit .env with your Supabase credentials and secret key
```

### 2. Run with Docker Compose

```bash
docker-compose up -d
```

### 3. Run locally (dev)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

---

## Environment Variables

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT signing secret (change in production!) |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `EDGE_GATEWAY_TOKEN` | Long-lived static token for Edge Gateway |
| `ALLOWED_ORIGINS` | JSON array of allowed CORS origins |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT access token TTL (default: 30) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token TTL (default: 7) |

---

## API Endpoints

### Auth `/api/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/login` | — | Get access + refresh tokens |
| `POST` | `/refresh` | refresh_token | Rotate access token |
| `GET`  | `/me` | JWT | Current user profile |
| `POST` | `/logout` | JWT | Revoke refresh token |

### Devices `/api/iot/devices`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET`    | `/` | JWT | List user's devices |
| `POST`   | `/` | JWT | Register new device |
| `GET`    | `/{id}` | JWT | Device detail |
| `PATCH`  | `/{id}` | JWT | Update metadata |
| `DELETE` | `/{id}` | JWT+ADMIN | Delete device |

### Telemetry `/api/iot/telemetry`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/` | EDGE_TOKEN | Ingest batch (≤ 100 records) |
| `GET`  | `/{device_id}/latest` | JWT | Latest reading |
| `GET`  | `/{device_id}/history` | JWT | Paginated history |

### Commands `/api/iot/commands`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST`  | `/` | JWT | Create command |
| `GET`   | `/pending` | EDGE_TOKEN | Poll pending commands |
| `PATCH` | `/{id}` | EDGE_TOKEN | Update command status |
| `GET`   | `/` | JWT | Command history |

### Alerts `/api/iot/alerts`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET`   | `/` | JWT | List alerts (filterable) |
| `PATCH` | `/{id}/read` | JWT | Mark as read |

---

## Database Migrations

Run migrations manually against your Supabase/PostgreSQL instance:

```bash
psql $DATABASE_URL -f migrations/001_initial_schema.sql
psql $DATABASE_URL -f migrations/002_add_indexes.sql
psql $DATABASE_URL -f migrations/003_add_alerts.sql
```

---

## Tests

```bash
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

---

## Authentication Flow

```
Client ──POST /api/auth/login──► API
                                  │ verify bcrypt password
                                  │ issue access_token (30m) + refresh_token (7d)
                                 ◄─ { access_token, refresh_token }

Client ──GET /api/... (Bearer access_token) ──► API
                                                 │ decode JWT
                                                 │ lookup user in DB
                                                ◄─ response

Client ──POST /api/auth/refresh (refresh_token) ─► API
                                                    │ verify token + DB match
                                                   ◄─ new access_token
```

---

## Security Notes

- Passwords hashed with **bcrypt** (passlib)
- JWT tokens signed with **HS256**
- Edge Gateway uses a **static long-lived token** (rotate via env var)
- Refresh tokens are stored in DB and invalidated on logout
- Rate limiting: **200 req/60s per IP** (in-process sliding window)

---

## Project Structure

```
agw-cloud-api/
├── app/
│   ├── main.py               # App factory
│   ├── config.py             # Pydantic Settings
│   ├── core/
│   │   ├── security.py       # JWT + bcrypt
│   │   ├── database.py       # asyncpg pool + get_db
│   │   └── middleware.py     # Logging + rate limiting
│   ├── models/               # SQLAlchemy ORM
│   ├── schemas/              # Pydantic v2
│   ├── services/             # Business logic (raw asyncpg)
│   ├── routers/              # FastAPI routers
│   └── dependencies/
│       └── auth.py           # JWT + edge token deps
├── migrations/               # SQL migration files
├── tests/                    # pytest-asyncio tests
├── Dockerfile
├── docker-compose.yml
└── .env.example
```
