from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from database.database import engine
import models
from routers import create_user
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))  # Load project root .env
#### this is for cloudflare deployment  ################
try:
    from workers import WorkerEntrypoint
    import asgi
    CLOUDFLARE_ENV = True
except ImportError:
    CLOUDFLARE_ENV = False
###################### End Cloudflare Deployment ############################


app = FastAPI()

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

models.Base.metadata.create_all(bind=engine)

@app.get("/")
async def root():
    return {"message": "Yaee! WORK AGATHA EDDE"}

@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/debug")
async def debug_connections():
    """Tests D1 and Supabase connections independently. Use this to diagnose errors."""
    import httpx
    from database.database import SessionLocal
    from database.database_space import SUPABASE_URL, SUPABASE_SERVICE_KEY
    results = {}

    # --- Test 1: D1 (local SQLite) ---
    try:
        db = SessionLocal()
        db.execute(__import__('sqlalchemy').text("SELECT 1"))
        db.close()
        results["D1_sqlite"] = {"status": "ok", "message": "Connected successfully"}
    except Exception as e:
        results["D1_sqlite"] = {"status": "error", "message": str(e)}

    # --- Test 2: Supabase REST ---
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

# @app.get("/db-test")
# async def test_db(req: Request):
#     try:
    
#         env = req.scope["env"]
#         db = env.DB
#         return {"status": "success", "message": "Successfully accessed D1 binding!"}
#     except KeyError:
#         return {"status": "error", "message": "Not running in Cloudflare Environment yet or 'env' missing from request."}
#     except Exception as e:
#         return {"status": "error", "message": str(e)}



# @app.post("/items/{name}")
# async def create_item(name: str, req: Request):
#     try:
#         env = req.scope["env"]
#         db = env.DB
        
#         result = await db.prepare(
#             "INSERT INTO test (name) VALUES (?1) RETURNING *"
#         ).bind(name).first()
        
#         return {"status": "success", "data": result.to_py()}
        
#     except KeyError:
#         return {"status": "error", "message": "Not running in Cloudflare Environment yet or 'env' missing from request."}
#     except Exception as e:
#         return {"status": "error", "message": str(e)}

# normal agi local nali run agala adike env variable set madini, ella andre error barute
############# This is for cloudflare################
if CLOUDFLARE_ENV:
    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            # This converts the Cloudflare request into FastAPI format
            return await asgi.fetch(app, request, self.env)
################# End cloudflare ##############################