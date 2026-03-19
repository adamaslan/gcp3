# Pipeline Summary — GCP3 Finance App

The GCP3 Finance App is built on a fully managed GCP infrastructure. The Python FastAPI backend runs on Cloud Run, with Cloud Build handling CI/CD — each `gcloud builds submit` triggers a Docker build, pushes the image to Artifact Registry, and deploys a new Cloud Run revision. Firestore serves as a 24-hour TTL cache layer, shielding the Finnhub API from redundant calls and keeping latency low. All secrets (API keys, project IDs) are injected at deploy time via Cloud Run environment variables or Secret Manager — never stored in code.

The Next.js 15 frontend is deployed to Vercel, written in strict TypeScript with Tailwind CSS for styling. Server Components handle all data fetching at the page level, calling Next.js API proxy routes that forward requests to the Cloud Run backend URL. Incremental Static Regeneration (`next: { revalidate: N }`) keeps pages fresh without hitting the backend on every request. This separation keeps the frontend stateless and the backend the single source of truth for all market data.

Gemini powers the AI-generated summaries surfaced in the Morning Brief and Industry Tracker features. The backend calls the Gemini API to synthesize raw Finnhub market data — index performance, sector rankings, and market tone — into readable prose. Results are cached in Firestore alongside the raw data, so Gemini is only invoked when the cache is cold. This keeps inference costs predictable while ensuring the AI commentary stays aligned with real, live market data rather than stale or fabricated figures.

## Workflow Diagram

```mermaid
flowchart TD
    subgraph DEV["Developer Machine"]
        CODE["Source Code"]
        CB["gcloud builds submit"]
    end

    subgraph GCP["GCP (us-central1)"]
        subgraph CICD["Cloud Build"]
            BUILD["Docker Build"]
            PUSH["Push to Artifact Registry"]
        end

        subgraph SECRETS["Secret Manager"]
            SM["API Keys / Env Vars\n(injected at deploy time)"]
        end

        subgraph BACKEND["Cloud Run — FastAPI Backend"]
            MAIN["main.py (routes)"]
            IND["industry.py"]
            MORN["morning.py"]
            FS["firestore.py (cache client)"]
        end

        subgraph CACHE["Firestore"]
            FSCOL["gcp3_cache\n(24h TTL)"]
        end
    end

    subgraph EXTERNAL["External APIs"]
        FINN["Finnhub\n(market data)"]
        GEM["Gemini API\n(AI summaries)"]
    end

    subgraph FRONTEND["Vercel — Next.js 15 (TypeScript)"]
        SC["Server Components"]
        PROXY["API Proxy Routes\n(src/app/api/)"]
        ISR["ISR revalidate"]
        USER["Browser / User"]
    end

    CODE --> CB --> BUILD --> PUSH --> BACKEND
    SM -->|env vars at deploy| BACKEND

    USER --> SC --> PROXY -->|BACKEND_URL| MAIN
    MAIN --> IND & MORN
    IND & MORN --> FS
    FS -->|cache miss| FINN
    FS -->|cache miss| GEM
    FS <-->|read / write| FSCOL
    GEM -->|AI summary| FS
    FINN -->|market data| FS
    FS -->|cached response| MAIN --> PROXY --> SC --> USER

    ISR -.->|revalidate| SC
```
