from fastapi import FastAPI, Request
from pydantic import BaseModel
from database.database import engine
import models # Here all the structures for th etables are defined
from routers import create_user
#### this is for cloudflare deployment  ################
try:
    from workers import WorkerEntrypoint
    import asgi
    CLOUDFLARE_ENV = True
except ImportError:
    CLOUDFLARE_ENV = False
###################### End Cloudflare Deployment ############################


app = FastAPI()

models.Base.metadata.create_all(bind=engine)# this is like create if not exists of sorts from the model definitions

@app.get("/")
async def root():
    return {"message": "Yaee! WORK AGATHA EDDE"}

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