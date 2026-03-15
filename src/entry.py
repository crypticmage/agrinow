import os
import sys

# Add the 'src' directory to sys.path so modules like database, models, and routers are found
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

# MUST be loaded before any other imports that call os.getenv() at module level
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(env_path)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from database.database import engine
import models
from routers import create_user, auth, users, sites, images


api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=True)

def verify_api_key(api_key: str = Depends(api_key_header)):
    expected_key = os.getenv("API_KEY")
    if not expected_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate API Key"
        )

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs ONCE on startup
    models.Base.metadata.create_all(bind=engine)
    yield
    # Cleanup on shutdown (optional)

app = FastAPI(
    lifespan=lifespan,
    # dependencies=[Depends(verify_api_key)], # For now we will stop this API Key thing (Full admele madona)
    title="Agrinow API",
    version="1.0.0",
    description=(
        "## Agrinow — Agricultural Operations API\n\n"
        "Manages users, authentication, and operational data for the Agrinow platform.\n\n"
        "### Security Model\n"
        "Agrinow uses a **zero-knowledge key scheme**:\n"
        "- Passwords are never stored. A 32-byte master key is derived via **Argon2id** (`salt=email`, `secret=server pepper`).\n"
        "- Each user has an **Ed25519 key pair**. The private key is AES-GCM encrypted with the master key and stored in Supabase.\n"
        "- Login re-derives the master key and decrypts the private key — a successful decryption proves the password is correct."
    ),
    contact={"name": "Agrinow Engineering"},
    license_info={"name": "Proprietary"},
)

LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN")



import logging

# ── Local File Logging + Console Output ────────────────────────────────────────
log_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "passenger_error.log")

class DualLoggerWriter:
    """Writes to both original stream (like Uvicorn console) AND to a local file."""
    def __init__(self, original_stream, filename):
        self.original_stream = original_stream
        self.filename = filename

    def write(self, message):
        self.original_stream.write(message)
        if message.strip():
            try:
                with open(self.filename, 'a', encoding='utf-8') as f:
                    from datetime import datetime
                    f.write(f"[{datetime.now()}] {message.strip()}\n")
            except Exception:
                pass

    def flush(self):
        self.original_stream.flush()

# Capture all print() statements and Uvicorn tracebacks into the local file
sys.stdout = DualLoggerWriter(sys.stdout, log_file_path)
sys.stderr = DualLoggerWriter(sys.stderr, log_file_path)

# Capture standard python logs (like httpx) into the local file
logging.basicConfig(
    handlers=[logging.FileHandler(log_file_path, encoding='utf-8')],
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

# Specifically enable httpx logging to see all HTTP requests in the text file
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.INFO)

# Initialize Logfire only if token is provided
if LOGFIRE_TOKEN:
    import logfire
    logfire.configure(token=LOGFIRE_TOKEN)
    logfire.instrument_fastapi(app)
    # logfire.instrument_httpx()


# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",  
    allow_credentials=False,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# Templates for the registration form
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# models.Base.metadata.create_all(bind=engine)  # MOVED TO LIFESPAN

@app.get("/", summary="Health check", description="Returns a simple liveness message confirming the API is running.")
async def root():
    return {"message": "Agrinow API is running 🌾"}

@app.get("/debug/http")
async def debug_http():
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("https://translate.googleapis.com")
            return {"status": r.status_code, "reachable": True}
    except Exception as e:
        return {"reachable": False, "error": str(e)}

@app.get("/debug/env")
async def debug_env():
    token = os.getenv("GMAIL_TOKEN_FILE", "NOT SET")
    return {
        "first_50_chars": token[:50],
        "starts_with": token[0] if token else "empty",
        "length": len(token)
    }
    
@app.get("/register", response_class=HTMLResponse, summary="Registration form", description="Serves the HTML user-registration page.", include_in_schema=False)
async def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/login", response_class=HTMLResponse, summary="Login form", description="Serves the HTML login page.", include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/forgot-password", response_class=HTMLResponse, summary="Forgot password form", description="Serves the forgot password page.", include_in_schema=False)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})

@app.get("/reset-password", response_class=HTMLResponse, summary="Reset password form", description="Serves the password reset page.", include_in_schema=False)
async def reset_password_page(request: Request):
    return templates.TemplateResponse("reset_password.html", {"request": request})

@app.get("/change-password", response_class=HTMLResponse, summary="Change password form", description="Serves the password change page for logged-in users.", include_in_schema=False)
async def change_password_page(request: Request):
    return templates.TemplateResponse("change_password.html", {"request": request})

@app.get("/users-page", response_class=HTMLResponse, summary="Users dashboard", description="Serves the users listing dashboard (requires JWT in localStorage).", include_in_schema=False)
async def users_page(request: Request):
    return templates.TemplateResponse("users.html", {"request": request})

@app.get("/assign-site", response_class=HTMLResponse, summary="Assign Site UI", include_in_schema=False)
async def assign_site_page(request: Request):
    return templates.TemplateResponse("site_assignment.html", {"request": request})

@app.get("/org-chart", response_class=HTMLResponse, summary="Organization Chart UI", include_in_schema=False)
async def org_chart_page(request: Request):
    return templates.TemplateResponse("org_chart.html", {"request": request})

@app.get("/user-logs", response_class=HTMLResponse, summary="Users Logs UI", include_in_schema=False)
async def user_logs_page(request: Request):
    return templates.TemplateResponse("user_logs.html", {"request": request})

@app.get("/images-page", response_class=HTMLResponse, summary="Images UI", include_in_schema=False)
async def images_page(request: Request):
    return templates.TemplateResponse("images.html", {"request": request})

@app.get("/view-image", response_class=HTMLResponse, summary="Image Viewer", include_in_schema=False)
async def view_image_page(request: Request):
    return templates.TemplateResponse("image_view.html", {"request": request})

@app.get("/site-chat", response_class=HTMLResponse, summary="Site Chat UI", include_in_schema=False)
async def site_chat_page(request: Request):
    return templates.TemplateResponse("site_chat.html", {"request": request})

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
        
        # Also let's check what tables are in the DB
        inspector = sqlalchemy.inspect(engine)
        tables = inspector.get_table_names()
        
        results["primary_db"] = {"status": "ok", "message": "Connected successfully", "tables": tables}
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
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sites.router)
app.include_router(images.router)