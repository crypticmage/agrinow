# 🌾 Agrinow — Zero-Knowledge Auth API

> Secure user management service built with **FastAPI**, deployed on **Cloudflare Workers**, with a dual-database Zero-Knowledge key architecture.

---

## 🔐 Security Architecture

Agrinow follows a **Zero-Knowledge** design — your server never stores plain-text passwords or raw private keys.

```
User Password
      │
      ▼
 Argon2id KDF ──── (email as salt + server pepper + associated data)
      │
      ▼
  Master Key (32 bytes, never stored)
      │
      ├──► Encrypt Ed25519 Private Key ──► AES-GCM ──► Supabase (DB2)
      │
      └──► Public Key ──────────────────────────────► Cloudflare D1 (DB1)
```

| What | Where | How |
|---|---|---|
| User profile + Public key | Cloudflare D1 (SQL) | SQLAlchemy |
| Encrypted private key + nonce | Supabase PostgreSQL | SQLAlchemy + psycopg2 |
| Secrets (pepper, JWT key) | Cloudflare Secrets Store | `env.SECRET.get()` async |

---

## 🗂️ Project Structure

```
agrinow/
├── src/
│   ├── entry.py                   # FastAPI app entrypoint & Cloudflare Worker binding
│   ├── models.py                  # SQLAlchemy table definitions (Users)
│   ├── database/
│   │   ├── database.py            # Cloudflare D1 engine + local SQLite fallback
│   │   └── database_space.py      # Supabase PostgreSQL engine (UserKeys vault)
│   └── routers/
│       └── create_user.py         # POST /create_user endpoint
├── wrangler.jsonc                 # Cloudflare Worker deployment config
├── pyproject.toml                 # Python dependencies
└── .env                           # Local development secrets (never commit!)
```

---

## ⚙️ Tech Stack

| Layer | Technology |
|---|---|
| API Framework | [FastAPI](https://fastapi.tiangolo.com/) |
| Deployment | [Cloudflare Workers](https://workers.cloudflare.com/) (Python) |
| Primary DB | [Cloudflare D1](https://developers.cloudflare.com/d1/) (SQLite-compatible SQL) |
| Key Vault DB | [Supabase](https://supabase.com/) PostgreSQL |
| ORM | [SQLAlchemy](https://www.sqlalchemy.org/) |
| KDF | Argon2id (via `cryptography`) |
| Asymmetric Crypto | Ed25519 |
| Symmetric Encryption | AES-GCM (256-bit) |
| Secrets Management | [Cloudflare Secrets Store](https://developers.cloudflare.com/secrets-store/) |

---

## 🚀 Local Development

### Prerequisites
- Python 3.11+
- `pip install psycopg2-binary cryptography PyJWT fastapi sqlalchemy uvicorn`

### 1. Clone & set up virtual environment
```bash
git clone <your-repo-url>
cd agrinow
python -m venv env
env\Scripts\activate      # Windows
source env/bin/activate   # macOS/Linux
pip install -e .
```

### 2. Configure `.env`
```env
JWT_SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
ARGON2_SECRET_PEPPER=<generate same way>
ARGON2_ASSOCIATED_DATA=agrinow_auth_v1
SUPABASE_DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres
```

### 3. Run locally
```bash
cd src
uvicorn entry:app --reload
```
Open **http://127.0.0.1:8000/docs** for the interactive Swagger UI.

---

## ☁️ Cloudflare Deployment

### 1. Create Secrets Store vault & add secrets
```bash
# Create the store (one time only)
npx wrangler secrets-store store create agrinow-secrets --remote

# Get the Store ID
npx wrangler secrets-store store list --remote

# Add each secret (replace <STORE_ID> with real ID)
npx wrangler secrets-store secret create <STORE_ID> --name JWT_SECRET_KEY --scopes workers --remote
npx wrangler secrets-store secret create <STORE_ID> --name ARGON2_SECRET_PEPPER --scopes workers --remote
npx wrangler secrets-store secret create <STORE_ID> --name ARGON2_ASSOCIATED_DATA --scopes workers --remote
npx wrangler secrets-store secret create <STORE_ID> --name SUPABASE_DATABASE_URL --scopes workers --remote
```

### 2. Update `wrangler.jsonc`
Replace all `store_id` placeholder values with your actual Secrets Store ID.

### 3. Deploy
```bash
npx wrangler deploy
```

---

## 🗄️ Database Setup

### Cloudflare D1 — Users table
```bash
npx wrangler d1 execute agrinow --command "
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  phone TEXT UNIQUE,
  first_name TEXT, last_name TEXT,
  public_key TEXT, language TEXT, role TEXT,
  manager_id INTEGER, emp_type TEXT,
  is_active BOOLEAN, hire_date DATE,
  relive_date DATE, created_dt DATE
);"
```

### Supabase — UserKeys vault
Run in your **Supabase SQL Editor**:
```sql
CREATE TABLE user_keys (
    id                    BIGSERIAL PRIMARY KEY,
    user_id               BIGINT NOT NULL UNIQUE,
    encrypted_private_key TEXT NOT NULL,
    nonce                 TEXT NOT NULL
);
```

---

## 📋 API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/create_user/` | Register a new user |

### `POST /create_user/`
```json
{
  "username": "john_doe",
  "email": "john@example.com",
  "phone": "+1234567890",
  "first_name": "John",
  "last_name": "Doe",
  "password": "your_secure_password",
  "language": "en",
  "role": "farmer",
  "manager_id": null,
  "hire_date": "2025-01-15",
  "relive_date": null,
  "emp_type": "full_time"
}
```

---

## 🛡️ Security Guarantees

- **Passwords never stored** — used only to derive Master Key, then wiped from memory via `finally` block.
- **Private keys encrypted** — AES-GCM before storage; raw key wiped from memory immediately.
- **Hard fail on missing secrets** — missing pepper/JWT key returns `HTTP 500`, never silently falls back to a weak default.
- **Duplicate check first** — username/email is validated before any expensive crypto, preventing CPU exhaustion attacks.
- **Atomic creation** — if the Supabase key vault insert fails, the D1 user row is automatically rolled back. No orphaned records, ever.

---

## 📄 License
MIT