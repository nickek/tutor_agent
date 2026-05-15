#!/bin/bash
set -e

source .env

# Initialize variables
FRESH_MODE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fresh)
            FRESH_MODE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--fresh]"
            echo "  --fresh    Run in fresh mode"
            echo "  -h, --help Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Main script logic
if [ "$FRESH_MODE" = true ]; then

    # Generate encryption key if not exists
    if [ -z "$N8N_ENCRYPTION_KEY" ]; then
        echo "Creating n8n encryption key..."
        export N8N_ENCRYPTION_KEY=$(openssl rand -base64 32)
        sed -i "s|^N8N_ENCRYPTION_KEY=.*|N8N_ENCRYPTION_KEY=\"$N8N_ENCRYPTION_KEY\"|" .env
    fi
    if [ -z "$WEBUI_SECRET_KEY" ]; then
        echo "Creating open-webui encryption key..."
        export WEBUI_SECRET_KEY=$(openssl rand -base64 32)
        sed -i "s|^WEBUI_SECRET_KEY=.*|WEBUI_SECRET_KEY=\"$WEBUI_SECRET_KEY\"|" .env
    fi
    
    docker compose -f docker-compose.yml down -v
    sleep 2

    echo "Starting Services up..."
    docker compose -f docker-compose.yml up -d --build
    sleep 10

    echo "Restarting containers..."
    docker compose -f docker-compose.yml restart
    sleep 10

    source init_n8n.sh
    source init_webui.sh
    docker ps

else
    docker compose -f docker-compose.yml up -d
fi