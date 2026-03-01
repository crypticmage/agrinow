from fastapi import FastAPI

#### this is for cloudflare deployment  ################
try:
    from workers import WorkerEntrypoint
    import asgi
    CLOUDFLARE_ENV = True
except ImportError:
    CLOUDFLARE_ENV = False
###################### End Cloudflare Deployment ############################

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Yaee! WORK AGATHA EDDE"}


# normal agi local nali run agala adike env variable set madini, ella andre error barute
############# This is for cloudflare################
if CLOUDFLARE_ENV:
    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            # This converts the Cloudflare request into FastAPI format
            return await asgi.fetch(app, request, self.env)
################# End cloudflare ##############################