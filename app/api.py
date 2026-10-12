from fastapi import FastAPI

app = FastAPI(title="Fridge-to-Table")


@app.get("/health")
def health() -> dict:
    return {"ok": True}
