from fastapi import FastAPI
from workers import WorkerEntrypoint
import asgi

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Success! FastAPI is live on Cloudflare."}

# The entrypoint class Cloudflare looks for
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # This converts the Cloudflare request into FastAPI format
        return await asgi.fetch(app, request, self.env)
