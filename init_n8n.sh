#!/bin/bash

set -e

# Check if .env file exists
if [ ! -f .env ]; then
    echo "n8n - Error: .env file not found"
    exit 1
fi

source .env

# Check required environment variables
required_vars=("N8N_OWNER_EMAIL" "N8N_OWNER_PASSWORD" "N8N_OWNER_FIRST_NAME" "N8N_OWNER_LAST_NAME")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "n8n - Error: $var must be set in .env"
        exit 1
    fi
done

# Wait for n8n to be fully ready (DB migrations done, editor accessible)
echo "n8n - Waiting for n8n to be ready..."
until docker logs n8n 2>&1 | grep -q "Editor is now accessible via"; do
  echo "n8n -   Still starting..."
  sleep 3
done

# Bootstrap owner
echo "n8n - Setting up n8n owner..."
OWNER_RESPONSE=$(curl -s -X POST http://localhost:5678/rest/owner/setup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "'"$N8N_OWNER_EMAIL"'",
    "password": "'"$N8N_OWNER_PASSWORD"'",
    "firstName": "'"$N8N_OWNER_FIRST_NAME"'",
    "lastName": "'"$N8N_OWNER_LAST_NAME"'"
  }')

if [ -z "$OWNER_RESPONSE" ]; then
    echo "n8n - Warning: Owner setup request completed (may already exist)"
else
    echo "n8n - Owner setup response: $OWNER_RESPONSE"
fi

echo "n8n - Importing workflows..."
if ! docker exec -it n8n sh -c '
  for wf in /workflows/*.json; do
    [ -f "$wf" ] || continue
    echo "n8n - Importing $wf"
    n8n import:workflow --input="$wf" || echo "n8n - Warning: Failed to import $wf"
  done'; then
    echo "n8n - Warning: Some workflows may have failed to import"
fi

CRED_ID_POSTGRES_CHAT=$(echo -n "postgres-chat-memory" | md5sum | cut -c1-16)

# Create postgres chat memory credential json
echo "n8n - Creating Postgres credential file..."
if ! docker exec -i n8n sh -c 'cat > /tmp/postgres-credential.json' <<EOF
[
  {
    "id": "${CRED_ID_POSTGRES_CHAT}",
    "name": "Postgres (Chat Memory)",
    "type": "postgres",
    "data": {
      "host": "${SUPABASE_HOST:-postgres}",
      "port": ${SUPABASE_PORT:-5432},
      "database": "${POSTGRES_DB}",
      "user": "${SUPABASE_USER}",
      "password": "${SUPABASE_PASSWORD}"
    }
  }
]
EOF
then
    echo "n8n - Error: Failed to create Postgres credential file"
    exit 1
fi

echo "n8n - Importing Postgres credential..."
docker exec n8n n8n import:credentials --input=/tmp/postgres-credential.json \
  && echo "n8n - Postgres credential imported successfully!" \
  || echo "n8n - Credential import failed."

docker exec n8n rm -f /tmp/postgres-credential.json

CRED_ID_GOOGLE_DRIVE=$(echo -n "google-drive-oauth2" | md5sum | cut -c1-16)

echo "n8n - Creating Google Drive OAuth2 credential file..."
if ! docker exec -i n8n sh -c 'cat > /tmp/google-drive-credential.json' <<EOF
[
  {
    "id": "${CRED_ID_GOOGLE_DRIVE}",
    "name": "Google Drive OAuth2",
    "type": "googleDriveOAuth2Api",
    "data": {
      "clientId": "${GOOGLE_CLIENT_ID}",
      "clientSecret": "${GOOGLE_CLIENT_SECRET}"
    }
  }
]
EOF
then
    echo "n8n - Error: Failed to create Google Drive credential file"
    exit 1
fi

echo "n8n - Importing Google Drive OAuth2 credential..."
docker exec n8n n8n import:credentials --input=/tmp/google-drive-credential.json \
  && echo "n8n - Google Drive credential imported successfully!" \
  || echo "n8n - Google Drive credential import failed."

docker exec n8n rm -f /tmp/google-drive-credential.json

CRED_ID_SUPABASE=$(echo -n "supabase-api" | md5sum | cut -c1-16)

echo "n8n - Creating Supabase credential file..."
if ! docker exec -i n8n sh -c 'cat > /tmp/supabase-credential.json' <<EOF
[
  {
    "id": "${CRED_ID_SUPABASE}",
    "name": "Supabase",
    "type": "supabaseApi",
    "data": {
      "host": "${SUPABASE_URL}",
      "serviceRoleSecret": "${SUPABASE_SECRET}",
      "serviceRole": "${SUPABASE_SECRET}",
      "secret": "${SUPABASE_SECRET}"
    }
  }
]
EOF
then
    echo "n8n - Error: Failed to create Supabase credential file"
    exit 1
fi

echo "n8n - Importing Supabase credential..."
docker exec n8n n8n import:credentials --input=/tmp/supabase-credential.json \
  && echo "n8n - Supabase credential imported successfully!" \
  || echo "n8n - Supabase credential import failed."

docker exec n8n rm -f /tmp/supabase-credential.json

CRED_ID_ANTHROPIC=$(echo -n "anthropic-api" | md5sum | cut -c1-16)

echo "n8n - Creating Anthropic credential file..."
if ! docker exec -i n8n sh -c 'cat > /tmp/anthropic-credential.json' <<EOF
[
  {
    "id": "${CRED_ID_ANTHROPIC}",
    "name": "Anthropic",
    "type": "anthropicApi",
    "data": {
      "apiKey": "${ANTHROPIC_SECRET}"
    }
  }
]
EOF
then
    echo "n8n - Error: Failed to create Anthropic credential file"
    exit 1
fi

echo "n8n - Importing Anthropic credential..."
docker exec n8n n8n import:credentials --input=/tmp/anthropic-credential.json \
  && echo "n8n - Anthropic credential imported successfully!" \
  || echo "n8n - Anthropic credential import failed."

docker exec n8n rm -f /tmp/anthropic-credential.json

CRED_ID_OLLAMA=$(echo -n "ollama-api" | md5sum | cut -c1-16)

echo "n8n - Creating Ollama credential file..."
if ! docker exec -i n8n sh -c 'cat > /tmp/ollama-credential.json' <<EOF
[
  {
    "id": "${CRED_ID_OLLAMA}",
    "name": "Ollama",
    "type": "ollamaApi",
    "data": {
      "baseUrl": "http://ollama:11434"
    }
  }
]
EOF
then
    echo "n8n - Error: Failed to create Ollama credential file"
    exit 1
fi

echo "n8n - Importing Ollama credential..."
docker exec n8n n8n import:credentials --input=/tmp/ollama-credential.json \
  && echo "n8n - Ollama credential imported successfully!" \
  || echo "n8n - Ollama credential import failed."

docker exec n8n rm -f /tmp/ollama-credential.json

# docker exec n8n sh -c '
#   for wf in /workflows/*.json; do
#     [ -f "$wf" ] || continue
#     WF_NAME=$(basename "$wf" .json)
#     WF_ID=$(n8n list:workflow 2>/dev/null | grep "|${WF_NAME}$" | cut -d"|" -f1)
#     if [ -z "$WF_ID" ]; then
#       echo "ERROR: Could not find ID for $WF_NAME, skipping."
#       continue
#     fi
#     echo "Publishing $WF_NAME with ID: $WF_ID"
#     n8n publish:workflow --id="$WF_ID"
#     echo "Done: $wf"
#   done'

# echo "Restarting n8n to load published workflows..."
# if ! docker restart n8n; then
#     echo "Error: Failed to restart n8n"
#     exit 1
# fi

# echo "Waiting for n8n to come back up..."
# TIMEOUT=90
# ELAPSED=0
# RESTART_TIME=$(date -u +"%Y-%m-%dT%H:%M:%S")
# until docker logs n8n --since "$RESTART_TIME" 2>&1 | grep -q "Editor is now accessible via"; do
#   if [ $ELAPSED -ge $TIMEOUT ]; then
#     echo "Error: Timeout waiting for n8n to restart"
#     exit 1
#   fi
#   echo "Still waiting..."
#   sleep 3
#   ELAPSED=$((ELAPSED + 3))
# done
# echo "n8n is back up."
