from fastapi import FastAPI

from web.endpoints import scheduler_router

app = FastAPI(title="Fluent scheduler", description="Web interface for Fluent scheduler", version="0.1.0")

@app.get("/")
def root():
    return{"message" : "Fluent Scheduler web interface is running"}

app.include_router(router=scheduler_router.router)
