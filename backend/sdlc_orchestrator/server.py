"""FastAPI server: starts runs, streams agent events over WebSocket, accepts reviews.

The server runs generated tests on the machine it runs on, so it binds to
127.0.0.1 by default. Do not expose it to a network you do not trust.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel, Field

from . import __version__
from .config import get_settings
from .demo import get_scenario, make_demo_repo
from .graph import build_graph
from .llm import get_llm


class RunRequest(BaseModel):
    repo: str | None = Field(None, description="Path to a local git repository")
    base: str = "main"
    head: str = "HEAD"
    diff: str | None = Field(None, description="A unified diff to review instead of reading the repo")
    demo: bool = Field(False, description="Ignore the other fields and run on a generated sample repo")
    scenario: str = Field("invoicing", description="Which sample repo to generate when demo is set")


class ReviewRequest(BaseModel):
    decision: str = Field("approve", pattern="^(approve|reject)$")
    title: str | None = None
    note: str = ""
    dismissed: list[str] = []
    include_tests: bool = True
    apply_tests: bool = False


@dataclass
class Run:
    id: str
    request: dict
    status: str = "running"  # running | awaiting_review | done | error
    created: float = field(default_factory=time.time)
    events: list[dict] = field(default_factory=list)
    review_payload: dict | None = None
    report: dict | None = None
    error: str | None = None
    subscribers: set[asyncio.Queue] = field(default_factory=set)

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "request": self.request,
            "status": self.status,
            "created": self.created,
            "events": self.events,
            "review": self.review_payload,
            "report": self.report,
            "error": self.error,
        }


class RunManager:
    def __init__(self):
        self.settings = get_settings()
        self.llm = get_llm(self.settings)
        self.graph = build_graph(self.llm, self.settings)
        self.runs: dict[str, Run] = {}

    async def publish(self, run: Run, message: dict) -> None:
        if message.get("type") == "event":
            run.events.append(message)
        for q in list(run.subscribers):
            q.put_nowait(message)

    async def _status(self, run: Run, status: str) -> None:
        run.status = status
        await self.publish(run, {"type": "status", "status": status, "review": run.review_payload, "report": run.report, "error": run.error})

    async def _drive(self, run: Run, graph_input: Any) -> None:
        cfg = {"configurable": {"thread_id": run.id}}
        try:
            interrupted = False
            async for mode, chunk in self.graph.astream(graph_input, cfg, stream_mode=["custom", "updates"]):
                if mode == "custom":
                    await self.publish(run, chunk)
                elif "__interrupt__" in chunk:
                    interrupted = True
                    run.review_payload = chunk["__interrupt__"][0].value
                elif "finalize" in chunk:
                    run.report = chunk["finalize"]["report"]
            if interrupted:
                await self.publish(run, _event("orchestrator", "review", "Waiting for a human to approve, edit or reject"))
                await self._status(run, "awaiting_review")
            else:
                await self._status(run, "done")
        except Exception as e:  # surface failures to the dashboard instead of dying silently
            run.error = f"{type(e).__name__}: {e}"
            await self.publish(run, _event("orchestrator", "error", run.error))
            await self._status(run, "error")

    async def start(self, req: RunRequest) -> Run:
        data = req.model_dump()
        if req.demo:
            try:
                spec = get_scenario(req.scenario)
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
            repo = await asyncio.to_thread(make_demo_repo, None, spec.id)
            data = {"repo": str(repo), "base": spec.base, "head": spec.head, "diff": None, "demo": True, "scenario": spec.id}
        elif not req.diff:
            if not req.repo or not (Path(req.repo) / ".git").exists():
                raise HTTPException(400, "repo must be a path to a local git repository, or send a diff, or set demo")
        run = Run(id=uuid.uuid4().hex[:10], request=data)
        self.runs[run.id] = run
        graph_input = {"run_id": run.id, "repo": data.get("repo") or "", "base": data["base"], "head": data["head"], "diff": data.get("diff") or ""}
        asyncio.create_task(self._drive(run, graph_input))
        return run

    async def resume(self, run: Run, review: ReviewRequest) -> None:
        if run.status != "awaiting_review":
            raise HTTPException(409, f"run is {run.status}, not awaiting review")
        await self._status(run, "running")
        asyncio.create_task(self._drive(run, Command(resume=review.model_dump())))


def _event(agent: str, phase: str, message: str) -> dict:
    return {"type": "event", "agent": agent, "phase": phase, "message": message, "data": {}, "ts": time.time()}


def create_app(manager: RunManager | None = None) -> FastAPI:
    app = FastAPI(title="Patchwise", version=__version__)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])
    mgr = manager or RunManager()
    app.state.manager = mgr

    def get_run(run_id: str) -> Run:
        run = mgr.runs.get(run_id)
        if not run:
            raise HTTPException(404, "run not found")
        return run

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "version": __version__, "model": mgr.llm.name}

    @app.get("/api/runs")
    async def list_runs() -> list[dict]:
        runs = sorted(mgr.runs.values(), key=lambda r: r.created, reverse=True)
        return [{"id": r.id, "status": r.status, "created": r.created, "request": r.request} for r in runs]

    @app.post("/api/runs", status_code=201)
    async def create_run(req: RunRequest) -> dict:
        run = await mgr.start(req)
        return {"id": run.id}

    @app.get("/api/runs/{run_id}")
    async def run_detail(run_id: str) -> dict:
        return get_run(run_id).snapshot()

    @app.post("/api/runs/{run_id}/review")
    async def review(run_id: str, body: ReviewRequest) -> dict:
        await mgr.resume(get_run(run_id), body)
        return {"ok": True}

    @app.websocket("/ws/runs/{run_id}")
    async def run_socket(ws: WebSocket, run_id: str) -> None:
        await ws.accept()
        run = mgr.runs.get(run_id)
        if not run:
            await ws.close(code=4404)
            return
        q: asyncio.Queue = asyncio.Queue()
        run.subscribers.add(q)
        await ws.send_json({"type": "snapshot", "run": run.snapshot()})

        async def pump() -> None:
            while True:
                await ws.send_json(await q.get())

        sender = asyncio.create_task(pump())
        try:
            while True:
                msg = await ws.receive_json()
                if msg.get("type") == "review":
                    try:
                        await mgr.resume(run, ReviewRequest(**msg.get("review", {})))
                    except HTTPException as e:
                        await ws.send_json({"type": "error", "message": e.detail})
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            run.subscribers.discard(q)

    static = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if static.exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="dashboard")
    return app

