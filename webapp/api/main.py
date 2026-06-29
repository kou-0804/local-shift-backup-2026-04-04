from fastapi import FastAPI

app = FastAPI(title="勤務表 Web API", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}
