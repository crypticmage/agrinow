from fastapi import FastAPI
from workers import WorkerEntrypoint
import asgi


app = FastAPI()

@app.get("/")
async def root():
    return {
        "message": "FastAPI is running on Cloudflare Workers!",
        "location": "The Edge"
    }

@app.get("/status")
async def status():
    return {"status": "online", "framework": "FastAPI"}

# This is a test connection
# uvicron for cloudflare
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # asgi.fetch handles the conversion of Worker requests to FastAPI
        return await asgi.fetch(app, request, self.env)
