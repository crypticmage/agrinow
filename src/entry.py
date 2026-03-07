from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from database.database import engine
import models
from routers import create_user
import os
from dotenv import load_dotenv

# Load .env file for local development
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI(title="Agrinow API", version="1.0.0")

# Templates for the registration form
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Create all DB tables if they don't exist
models.Base.metadata.create_all(bind=engine)

@app.get("/")
async def root():
    return {"message": "Agrinow API is running 🌾"}

@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/debug")
async def debug_connections():
    """Tests PostgreSQL and Supabase connections independently."""
    import httpx
    import sqlalchemy
    from database.database import SessionLocal
    from database.database_space import SUPABASE_URL, SUPABASE_SERVICE_KEY
    results = {}

    # --- Test 1: Primary DB (PostgreSQL on Render) ---
    try:
        db = SessionLocal()
        db.execute(sqlalchemy.text("SELECT 1"))
        db.close()
        results["primary_db"] = {"status": "ok", "message": "Connected successfully"}
    except Exception as e:
        results["primary_db"] = {"status": "error", "message": str(e)}

    # --- Test 2: Supabase REST (key vault) ---
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

app.include_router(create_user.router)