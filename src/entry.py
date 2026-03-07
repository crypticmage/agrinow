from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from database.database import engine
import models
from routers import create_user
import os

# ── Detect Cloudflare Workers environment FIRST ────────────────────────────
try:
    from workers import WorkerEntrypoint
    import asgi
    CLOUDFLARE_ENV = True
except ImportError:
    CLOUDFLARE_ENV = False

# ── Load .env only on local dev (file system not available on Cloudflare) ──
if not CLOUDFLARE_ENV:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    except ImportError:
        pass  # python-dotenv not installed, skip silently

app = FastAPI()

# ── Templates: only init on local (Cloudflare bundles templates differently) ──
if not CLOUDFLARE_ENV:
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

    @app.get("/register", response_class=HTMLResponse)
    async def register_form(request: Request):
        return templates.TemplateResponse("register.html", {"request": request})

    @app.get("/debug")
    async def debug_connections():
        """Tests D1 and Supabase connections independently."""
        import httpx
        from database.database import SessionLocal
        from database.database_space import SUPABASE_URL, SUPABASE_SERVICE_KEY
        results = {}

        # --- D1 / SQLite ---
        try:
            import sqlalchemy
            db = SessionLocal()
            db.execute(sqlalchemy.text("SELECT 1"))
            db.close()
            results["D1_sqlite"] = {"status": "ok", "message": "Connected successfully"}
        except Exception as e:
            results["D1_sqlite"] = {"status": "error", "message": str(e)}

        # --- Supabase REST ---
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/user_keys?limit=1",
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
                    },
                    timeout=5
                )
            results["supabase_rest"] = {
                "status": "ok" if resp.status_code < 400 else "error",
                "http_status": resp.status_code,
                "message": resp.text[:200]
            }
        except Exception as e:
            results["supabase_rest"] = {"status": "error", "message": str(e)}

        return results

# ── Create DB tables only on local (on Cloudflare, D1 tables pre-exist) ───
if not CLOUDFLARE_ENV:
    try:
        models.Base.metadata.create_all(bind=engine)
    except Exception:
        pass  # Silently skip if DB not available at startup

@app.get("/")
async def root():
    return {"message": "Yaee! WORK AGATHA EDDE"}

app.include_router(create_user.router)

# ── Cloudflare Worker entrypoint ───────────────────────────────────────────
if CLOUDFLARE_ENV:
    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            return await asgi.fetch(app, request, self.env)