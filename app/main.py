from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from data_prep.classifier import ensure_model as warm_up_classifier
from drafts.adapter import warmup as warm_up_drafts
from fastapi import FastAPI, Response
from retrieval.rules_index import warm_up_index

from . import usage
from .pipeline import triage
from .schemas import TriageRequest, TriageResponse

load_dotenv()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    warm_up_classifier()
    warm_up_index()
    warm_up_drafts()
    yield


app = FastAPI(title="Support Copilot", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/triage", response_model=TriageResponse)
def triage_endpoint(req: TriageRequest, response: Response) -> TriageResponse:
    usage.reset()
    result = triage(req)
    totals = usage.snapshot()
    response.headers["X-Cost-Usd"] = f"{totals['usd']:.6f}"
    response.headers["X-Tokens-In"] = str(totals["in"])
    response.headers["X-Tokens-Out"] = str(totals["out"])
    return result
