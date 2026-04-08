#!/bin/bash
# Phase 1 GCP Configuration Commands
# Run these after deploying the code changes
# Date: 2026-04-07

set -e

# Ensure GCP_PROJECT_ID is set
if [ -z "$GCP_PROJECT_ID" ]; then
    echo "Error: GCP_PROJECT_ID not set"
    exit 1
fi

echo "=========================================="
echo "Phase 1: Firestore TTL & Cloud Run Setup"
echo "=========================================="

# 1A. Enable native Firestore TTL on expires_at field
echo ""
echo "1️⃣  Enabling Firestore native TTL on expires_at field..."
gcloud firestore fields ttls update expires_at \
  --collection-group=gcp3_cache \
  --enable-ttl \
  --project=$GCP_PROJECT_ID

echo "✅ TTL enabled. Verifying..."
gcloud firestore fields describe expires_at --project=$GCP_PROJECT_ID | grep -A2 ttlConfig

# 1B. Set Cloud Run min instances to 1
echo ""
echo "2️⃣  Setting Cloud Run min-instances=1..."
gcloud run services update gcp3-backend \
  --region us-central1 \
  --min-instances=1 \
  --project=$GCP_PROJECT_ID

echo "✅ Min instances set. Verifying..."
gcloud run services describe gcp3-backend \
  --region us-central1 \
  --project=$GCP_PROJECT_ID | grep -A1 minInstances

# Phase 3: Add Cloud Scheduler jobs (if not already present)
echo ""
echo "3️⃣  Checking for existing Cloud Scheduler jobs..."

# Get the backend service URL
BACKEND_URL=$(gcloud run services describe gcp3-backend \
  --region us-central1 \
  --project=$GCP_PROJECT_ID \
  --format='value(status.url)')

echo "Backend URL: $BACKEND_URL"

# Verify SCHEDULER_SECRET is set
if [ -z "$SCHEDULER_SECRET" ]; then
    echo "⚠️  Warning: SCHEDULER_SECRET not set. You'll need to set it when creating scheduler jobs."
else
    echo "SCHEDULER_SECRET is configured ✅"
fi

echo ""
echo "4️⃣  Cloud Scheduler job creation (run manually or use gcloud):"
echo ""
echo "Pre-Market Warmup (8:30 AM ET):"
echo "gcloud scheduler jobs create http gcp3-premarket-warmup \\"
echo "  --schedule='30 12 * * 1-5' \\"
echo "  --http-method=POST \\"
echo "  --uri='$BACKEND_URL/refresh/premarket' \\"
echo "  --headers='X-Scheduler-Token=\$SCHEDULER_SECRET' \\"
echo "  --time-zone='UTC' \\"
echo "  --location=us-central1 \\"
echo "  --project=$GCP_PROJECT_ID"
echo ""
echo "Nightly Cache Purge (2:00 AM ET):"
echo "gcloud scheduler jobs create http gcp3-nightly-cache-purge \\"
echo "  --schedule='0 6 * * *' \\"
echo "  --http-method=POST \\"
echo "  --uri='$BACKEND_URL/admin/purge-cache' \\"
echo "  --headers='X-Scheduler-Token=\$SCHEDULER_SECRET' \\"
echo "  --time-zone='UTC' \\"
echo "  --location=us-central1 \\"
echo "  --project=$GCP_PROJECT_ID"
echo ""

# Verify existing jobs
echo "5️⃣  Existing Cloud Scheduler jobs:"
gcloud scheduler jobs list --location=us-central1 --project=$GCP_PROJECT_ID || echo "No jobs found."

echo ""
echo "=========================================="
echo "Phase 1 Setup Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "✅ Firestore TTL enabled on expires_at"
echo "✅ Cloud Run min-instances set to 1"
echo "📋 Cloud Scheduler jobs: create manually using commands above"
echo ""
echo "Next steps:"
echo "1. Deploy code: gcloud builds submit --config cloudbuild.yaml"
echo "2. Create scheduler jobs: copy commands above"
echo "3. Monitor Firestore collection size over 24 hours"
echo ""
