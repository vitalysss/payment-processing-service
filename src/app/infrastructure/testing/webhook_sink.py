from fastapi import FastAPI, Response, status

app = FastAPI(title="Webhook test sink", docs_url=None, redoc_url=None)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def receive_webhook() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/fail", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
async def reject_webhook() -> Response:
    return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
