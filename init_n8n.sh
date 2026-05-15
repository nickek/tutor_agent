#!/bin/bash

set -e

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found"
    exit 1
fi

source .env

# Check required environment variables
required_vars=("N8N_OWNER_EMAIL" "N8N_OWNER_PASSWORD" "N8N_OWNER_FIRST_NAME" "N8N_OWNER_LAST_NAME")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Error: $var must be set in .env"
        exit 1
    fi
done

# Wait for n8n to be ready
until curl -f http://localhost:5678/healthz 2>/dev/null; do
  echo "Waiting for n8n to be healthy..."
  sleep 3
done

# Bootstrap owner
echo "Setting up n8n owner..."
OWNER_RESPONSE=$(curl -s -X POST http://localhost:5678/rest/owner/setup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "'"$N8N_OWNER_EMAIL"'",
    "password": "'"$N8N_OWNER_PASSWORD"'",
    "firstName": "'"$N8N_OWNER_FIRST_NAME"'",
    "lastName": "'"$N8N_OWNER_LAST_NAME"'"
  }')

if [ -z "$OWNER_RESPONSE" ]; then
    echo "Warning: Owner setup request completed (may already exist)"
else
    echo "Owner setup response: $OWNER_RESPONSE"
fi

echo "Importing workflows..."
if ! docker exec -it n8n sh -c '
  for wf in /workflows/*.json; do
    [ -f "$wf" ] || continue
    echo "Importing $wf"
    n8n import:workflow --input="$wf" || echo "Warning: Failed to import $wf"
  done'; then
    echo "Warning: Some workflows may have failed to import"
fi

docker exec n8n sh -c '
  for wf in /workflows/*.json; do
    [ -f "$wf" ] || continue
    WF_NAME=$(basename "$wf" .json)
    WF_ID=$(n8n list:workflow 2>/dev/null | grep "|${WF_NAME}$" | cut -d"|" -f1)
    if [ -z "$WF_ID" ]; then
      echo "ERROR: Could not find ID for $WF_NAME, skipping."
      continue
    fi
    echo "Publishing $WF_NAME with ID: $WF_ID"
    n8n publish:workflow --id="$WF_ID"
    echo "Done: $wf"
  done'

echo "Restarting n8n to load published workflows..."
if ! docker restart n8n; then
    echo "Error: Failed to restart n8n"
    exit 1
fi

echo "Waiting for n8n to come back up..."
TIMEOUT=60
ELAPSED=0
until curl -sf http://localhost:5678/healthz 2>/dev/null; do
  if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "Error: Timeout waiting for n8n to restart"
    exit 1
  fi
  echo "Still waiting..."
  sleep 3
  ELAPSED=$((ELAPSED + 3))
done
echo "n8n is back up."