# SAT Doubt Solver

Stuck on an SAT question? Paste it or snap a photo — get a step-by-step
explanation plus 3 similar practice problems. AI-powered, no $8,000 tutor.

## Run locally

```bash
pip install -r requirements.txt
OPENROUTER_API_KEY=sk-or-... python -m uvicorn server:app --port 8000
```

Optional: `OPENROUTER_MODEL` (default `openai/gpt-4o-mini`).

## Deploy (Render)

Docker web service, free tier. Set env var `OPENROUTER_API_KEY` in the
Render dashboard — never commit it.

## API

`POST /api/solve` → `{ "text": "...", "image": "data:image/...;base64,..." }`
`GET /healthz` → status
