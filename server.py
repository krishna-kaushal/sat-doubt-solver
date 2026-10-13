#!/usr/bin/env python3
"""SAT Doubt Solver — MVP.

Paste an SAT question (text and/or photo), get a step-by-step explanation
plus 3 similar practice problems, powered by OpenRouter.

Env:
    OPENROUTER_API_KEY  required — OpenRouter API key
    OPENROUTER_MODEL    model id (default: openai/gpt-4o-mini)
    PORT                default 8000
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
API_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are an expert SAT tutor helping a student prepare for the digital SAT.
You receive one question as text and/or an image.

Respond with JSON ONLY (no markdown fences, no commentary) in exactly this shape:
{
  "subject": "Math" or "Reading and Writing",
  "topic": "short topic label, e.g. 'Systems of linear equations'",
  "explanation": "step-by-step explanation in markdown. For Math: show each working step clearly. For Reading and Writing: explain why the correct answer is right AND why each wrong choice is wrong (trap analysis). End with a one-line 'Key takeaway'.",
  "problems": [
    {"question": "an original practice problem in official digital-SAT style on the same topic and similar difficulty", "answer": "the correct answer, concise", "hint": "one short hint"},
    {"question": "...", "answer": "...", "hint": "..."},
    {"question": "...", "answer": "...", "hint": "..."}
  ]
}

Rules:
- The 3 practice problems must be ORIGINAL (never copies of official College Board questions), in digital SAT style and format.
- Keep the explanation focused, student-friendly, and free of jargon.
- Write maths in plain text (e.g. 2(x - 1) = 2, x = 2). Do NOT use LaTeX delimiters like \\( \\) or \\[ \\].
- If the image is unclear or no question is detectable, set "subject" to "Unknown" and explain what you need in "explanation", with an empty "problems" array."""

# Matches a backslash NOT followed by a valid JSON escape character.
# Used to repair model output like \( or \. which is invalid JSON.
_INVALID_ESCAPE_RE = re.compile(r'\\(?![\"\\/bfnrtu])')


def _repair_invalid_escapes(s: str) -> str:
    """Drop backslashes that start invalid JSON escapes (e.g. \\( -> ()."""
    return _INVALID_ESCAPE_RE.sub("", s)


def _try_parse(s: str) -> dict | None:
    """Parse s as JSON, repairing invalid escapes once on failure."""
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        try:
            data = json.loads(_repair_invalid_escapes(s))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def extract_json(raw: str) -> dict | None:
    """Robustly extract the JSON object from a model response."""
    raw = raw.strip()
    # 1. direct parse
    data = _try_parse(raw)
    if data is not None:
        return data
    # 2. fenced code block anywhere in the text
    for m in re.finditer(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL):
        data = _try_parse(m.group(1).strip())
        if data is not None:
            return data
    # 3. outermost { ... } span
    start, end = raw.find("{"), raw.rfind("}")
    if 0 <= start < end:
        data = _try_parse(raw[start : end + 1])
        if data is not None:
            return data
    return None

# simple in-memory rate limit: 12 solves / hour / IP (protects API credits)
RATE_LIMIT = 12
WINDOW_S = 3600
_hits: dict[str, deque] = defaultdict(deque)


def check_rate_limit(ip: str) -> None:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests — try again later.")
    q.append(now)


def call_openrouter(text: str, image_data_url: str | None) -> dict:
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Server is missing its OpenRouter API key.")
    if image_data_url:
        content: object = [
            {"type": "text", "text": text or "Solve this SAT question step by step."},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    else:
        content = text
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.3,
        "max_tokens": 2500,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
            "HTTP-Referer": "https://sat-doubt-solver.onrender.com",
            "X-Title": "SAT Doubt Solver",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network / provider error
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}")
    try:
        raw = payload["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise HTTPException(status_code=502, detail="Unexpected AI provider response.")
    raw = raw.strip()
    data = extract_json(raw)
    if data is None:
        raise HTTPException(status_code=502, detail="Could not parse the AI response.")
    if "explanation" not in data:
        raise HTTPException(status_code=502, detail="Incomplete AI response.")
    data.setdefault("problems", [])
    data.setdefault("subject", "Unknown")
    data.setdefault("topic", "")
    return data


class SolveRequest(BaseModel):
    text: str = ""
    image: str = ""  # data URL (data:image/...;base64,...) or ""


app = FastAPI(title="SAT Doubt Solver")
PUBLIC = Path(__file__).parent / "public"


@app.get("/healthz")
def healthz():
    return {"ok": True, "model": MODEL, "key_configured": bool(API_KEY)}


@app.post("/api/solve")
def solve(req: SolveRequest, request: Request):
    text = (req.text or "").strip()
    image = (req.image or "").strip()
    if not text and not image:
        raise HTTPException(status_code=400, detail="Provide a question as text or an image.")
    if image and not image.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Image must be a data URL.")
    if len(text) > 6000:
        raise HTTPException(status_code=400, detail="Question text is too long.")
    ip = request.client.host if request.client else "unknown"
    check_rate_limit(ip)
    return JSONResponse(call_openrouter(text, image or None))


app.mount("/", StaticFiles(directory=PUBLIC, html=True), name="public")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(PUBLIC / "index.html")
