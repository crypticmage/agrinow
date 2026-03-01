from fastapi import FastAPI
from workers import WorkerEntrypoint
import asgi

# 1. Initialize your FastAPI app
app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello from FastAPI on the Edge!"}

@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello, {name}!"}

# 2. The Worker Entrypoint
# This is what Cloudflare calls when a request hits your URL
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # We use Cloudflare's built-in asgi.fetch to handle the routing
        return await asgi.fetch(app, request, self.env)
