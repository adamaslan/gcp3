# GCP3 Finance App

Minimal full-stack finance app. Two features: **Industry Tracker** and **Morning Brief**.

## Stack

- **Frontend**: Next.js 15, Tailwind CSS → Cloud Run
- **Backend**: Python FastAPI → Cloud Run
- **Data**: Firestore (cache), Finnhub (market data)
- **Infra**: GCP Cloud Run, Cloud Build

## Features

| Feature | Description |
|---------|-------------|
| Industry Tracker | 11-sector ETF performance rankings, refreshed daily |
| Morning Brief | Market tone, index performance, daily summary |

## Structure

```
gcp3/
├── backend/          FastAPI Cloud Run service
│   ├── main.py       Entry point + routes
│   ├── industry.py   Industry tracker logic
│   ├── morning.py    Morning brief logic
│   ├── firestore.py  Firestore cache client
│   ├── Dockerfile
│   └── cloudbuild.yaml
└── frontend/         Next.js Cloud Run service
    ├── src/app/      Pages + API routes
    ├── src/components/
    ├── Dockerfile
    └── cloudbuild.yaml
```

## Deploy

### Backend
```bash
cd backend
gcloud builds submit --config cloudbuild.yaml
```

### Frontend
```bash
cd frontend
gcloud builds submit --config cloudbuild.yaml
```

## Environment Variables

Copy `.env.example` → `.env` and fill in real values (never commit).

Backend secrets should be set via Cloud Run environment variables or Secret Manager.
