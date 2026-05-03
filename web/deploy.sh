#!/usr/bin/env bash
# Cloud Run deploy with Secret Manager + IAM in one shot.
# Per hackathon-playbook. Designed to run from Cloud Shell (shell.cloud.google.com).
#
# Usage: ./deploy.sh PROJECT_ID GEMINI_API_KEY [REGION]
# Default region: asia-south1 (Mumbai — closest to Indian users)

set -euo pipefail

PROJECT_ID="${1:?Usage: ./deploy.sh PROJECT_ID GEMINI_API_KEY [REGION]}"
API_KEY="${2:?Usage: ./deploy.sh PROJECT_ID GEMINI_API_KEY [REGION]}"
REGION="${3:-asia-south1}"
SERVICE="${SERVICE:-matdaan-mitra}"
SECRET_NAME="${SECRET_NAME:-matdaan-gemini-key}"

echo "→ Project: $PROJECT_ID  |  Region: $REGION  |  Service: $SERVICE"

gcloud config set project "$PROJECT_ID" --quiet
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  --quiet

# --- Secret Manager: store/update API key ----------------------------------
if gcloud secrets describe "$SECRET_NAME" >/dev/null 2>&1; then
  echo "→ Updating existing secret $SECRET_NAME"
  echo -n "$API_KEY" | gcloud secrets versions add "$SECRET_NAME" --data-file=- --quiet
else
  echo "→ Creating new secret $SECRET_NAME"
  echo -n "$API_KEY" | gcloud secrets create "$SECRET_NAME" --data-file=- --replication-policy=automatic --quiet
fi

# --- Grant Cloud Build / Run permissions to default Compute SA -------------
PROJECT_NUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
SA="${PROJECT_NUM}-compute@developer.gserviceaccount.com"

for role in \
  roles/cloudbuild.builds.builder \
  roles/run.builder \
  roles/storage.objectViewer \
  roles/logging.logWriter \
  roles/artifactregistry.writer \
  roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA" --role="$role" --condition=None --quiet >/dev/null
done

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor" --quiet >/dev/null

# --- Deploy ---------------------------------------------------------------
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-secrets "GOOGLE_AI_API_KEY=${SECRET_NAME}:latest" \
  --set-env-vars "GEMINI_MODEL=gemini-2.5-flash" \
  --memory 512Mi \
  --min-instances 1 \
  --max-instances 3 \
  --cpu-boost \
  --timeout 60 \
  --quiet

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
REVISION=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.latestReadyRevisionName)')
echo ""
echo "✅ Deployed: $URL"
echo "   Revision: $REVISION"
echo ""
echo "→ Smoke test:"
curl -s "${URL}/api/health" | python3 -m json.tool || echo "(install python3 in your shell for pretty output)"
