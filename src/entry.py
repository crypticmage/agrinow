import os
from dotenv import load_dotenv

# MUST be loaded before any other imports that call os.getenv() at module level
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from database.database import engine
import models
from routers import create_user, auth, users, sites

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=True)

def verify_api_key(api_key: str = Depends(api_key_header)):
    expected_key = os.getenv("API_KEY")
    if not expected_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate API Key"
        )

app = FastAPI(
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

# Logging setup with relative path
log_file = os.path.join(os.path.dirname(__file__), "..", "passenger_error.log")

with open(log_file, "a", encoding='utf-8') as f:
    f.write("[STARTUP] FastAPI app object created\n")

# Middleware to log all requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    with open(log_file, "a", encoding='utf-8') as f:
        f.write(f"[REQUEST] {request.method} {request.url.path}\n")
    try:
        response = await call_next(request)
        with open(log_file, "a", encoding='utf-8') as f:
            f.write(f"[RESPONSE] {request.method} {request.url.path} - Status: {response.status_code}\n")
        return response
    except Exception as e:
        with open(log_file, "a", encoding='utf-8') as f:
            f.write(f"[ERROR] {request.method} {request.url.path} - Exception: {str(e)}\n")
        raise

origins = [
    "https://cmdev.rakshitr.co.in",
    "https://api-dev.rakshitr.co.in",
    "http://localhost:3000", # Good for local testing
]
# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# Templates for the registration form
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Create all DB tables if they don't exist
models.Base.metadata.create_all(bind=engine)

@app.get("/", summary="Health check", description="Returns a simple liveness message confirming the API is running.")
async def root():
    return {"message": "Agrinow API is running 🌾"}

@app.get("/register", response_class=HTMLResponse, summary="Registration form", description="Serves the HTML user-registration page.", include_in_schema=False)
async def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/login", response_class=HTMLResponse, summary="Login form", description="Serves the HTML login page.", include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

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
