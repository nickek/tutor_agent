#!/bin/bash

set -e

# Check if .env file exists
if [ ! -f .env ]; then
    echo "open-webui - Error: .env file not found"
    exit 1
fi

source .env

# Check required environment variables
if [ -z "$WEBUI_ADMIN_EMAIL" ] || [ -z "$WEBUI_ADMIN_PASSWORD" ]; then
    echo "open-webui - Error: WEBUI_ADMIN_EMAIL and WEBUI_ADMIN_PASSWORD must be set in .env"
    exit 1
fi

export OPEN_WEBUI_URL="http://localhost:3000"
export FUNCTION_FILE="/functions/n8n-pipe.json"
export MODELS_FILE="/models/models.json"

# Wait for n8n to be ready
until curl -f ${OPEN_WEBUI_URL}/health 2>/dev/null; do
  echo "open-webui - Waiting for open-webui to be healthy..."
  sleep 3
done

echo "open-webui - Open WebUI is ready!"

# Login and get token
echo "open-webui - Logging in..."

RESPONSE=$(curl -s -X POST \
  "${OPEN_WEBUI_URL}/api/v1/auths/signin" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${WEBUI_ADMIN_EMAIL}\",\"password\":\"${WEBUI_ADMIN_PASSWORD}\"}")

TOKEN=$(echo "$RESPONSE" | sed -n 's/.*"token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')

if [ -z "$TOKEN" ]; then
    echo "open-webui - Login failed!"
    echo "open-webui - Response was: $RESPONSE"
    exit 1
fi

echo "open-webui - Successfully got token..."


# Creating pipe function to connect with n8n
FUNCTION_JSON=$(docker exec -it open-webui cat ${FUNCTION_FILE})

if [ -z "$FUNCTION_JSON" ]; then
    echo "open-webui - Error: Failed to read function file from container"
    exit 1
fi

echo "open-webui - Creating n8n_pipe function..."
FUNCTION_RESPONSE=$(curl -X POST \
  "${OPEN_WEBUI_URL}/api/v1/functions/create" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${FUNCTION_JSON}")

if [ -z "$FUNCTION_RESPONSE" ]; then
    echo "open-webui - Error: Failed to create function"
    exit 1
fi

echo "${FUNCTION_RESPONSE}"

# Enable Merlin function
echo "open-webui - Enabling function in database..."
if ! docker exec -it postgres-tutor psql -U ${POSTGRES_USER} -d openwebui -c "UPDATE function SET is_active=true WHERE id='tutor_agent';" 2>/dev/null; then
    echo "open-webui - Warning: Failed to enable function in database"
fi

curl -s -X POST \
  "${OPEN_WEBUI_URL}/api/v1/users/user/settings/update" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$(cat <<EOF
{
  "ui": {
    "version": "0.7.2",
    "autoFollowUps": ${ENABLE_FOLLOW_UP_GENERATION},
    "autoTags": ${ENABLE_FOLLOW_UP_GENERATION},
    "title": {
      "auto": ${ENABLE_FOLLOW_UP_GENERATION}
    }
  }
}
EOF
)" | python3 -m json.tool

# Get base64 encoded image
echo "Extracting logos uri..."
TUTOR_IMG_BASE64=$(docker exec -i open-webui base64 -w 0 /app/backend/static/assets/Tutor_agent.png 2>/dev/null || echo "")
if [ -z "$TUTOR_IMG_BASE64" ]; then
    echo "Warning: Failed to extract Tutor logo"
fi
TUTOR_IMG_DATA_URI="data:image/png;base64,${TUTOR_IMG_BASE64}"

# Import model settings
MODELS_JSON=$(docker exec -it open-webui cat ${MODELS_FILE})

if [ -z "$MODELS_JSON" ]; then
    echo "Error: Failed to read models file from container"
    exit 1
fi

TMP_URI=$(mktemp)
printf '%s' "$TUTOR_IMG_DATA_URI" > "$TMP_URI"
MODELS_JSON=$(python3 -c "
import sys
uri = open(sys.argv[1]).read()
print(sys.stdin.read().replace('assets/Tutor_agent.png', uri), end='')
" "$TMP_URI" <<< "$MODELS_JSON")
rm -f "$TMP_URI"

echo "Importing model details..."

TMP_PAYLOAD=$(mktemp)
trap 'rm -f "${TMP_PAYLOAD}"' EXIT

printf '{"models": %s}' "${MODELS_JSON}" > "${TMP_PAYLOAD}"

MODEL_RESPONSE=$(curl -X POST "${OPEN_WEBUI_URL}/api/v1/models/import" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data "@${TMP_PAYLOAD}")

if [ -z "$MODEL_RESPONSE" ]; then
    echo "Error: Failed to import models"
    exit 1
fi

echo "${MODEL_RESPONSE}"
