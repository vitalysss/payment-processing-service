from fastapi import Depends, FastAPI

from app.infrastructure.config import settings
from app.presentation.api.auth import require_api_key
from app.presentation.api.routes import router

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(router)


@app.get("/health", include_in_schema=False, dependencies=[Depends(require_api_key)])
async def health() -> dict[str, str]:
    return {"status": "ok"}
