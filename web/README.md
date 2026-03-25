# Backfill Web

Vercel-friendly TypeScript frontend for the Backfill support-layer website.

## Local setup

1. Install dependencies:
   `npm install`
2. Copy envs:
   `cp .env.example .env.local`
3. Start the FastAPI backend separately on `http://127.0.0.1:8000`
4. Run the frontend:
   `npm run dev`

## Vercel

- Set the project Root Directory to `web`
- Set `BACKFILL_API_BASE_URL` to your deployed FastAPI backend URL
- Build command: `npm run build`
- Output setting: Next.js default
