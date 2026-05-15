# Local AI Workshop

This project provides a complete local ai workshop, equipped with local Large Language Model (LLM) setup using Ollama, Open WebUI for a user-friendly interface, and n8n for workflow automation.

---

## Overview

This setup includes three main services:

- **Ollama**: Open-source LLM server for running models locally with GPU support
- **Open WebUI**: User-friendly web interface for interacting with LLMs
- **n8n**: Workflow automation platform for integrating LLMs into your workflows

All services run in Docker containers with persistent storage and are configured to work together seamlessly.

---

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Nvidia Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (for GPU support)
- Linux OS

---

## Quick Start

### 1. Install Required Dependencies

Install Docker and Docker Compose by following the official documentation for your OS:
- [Docker Install Guide](https://docs.docker.com/engine/install/)
- [Docker Compose Install](https://docs.docker.com/compose/install/)
- [Nvidia Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (required for GPU acceleration)

### 2. Clone the Project Repository

```bash
git clone <your-repo-url>
cd local_ai_workshop/
```

**Note**: The `ollama`, `open-webui` and `n8n` volumes are managed by Docker and don't require manual directory creation.

### 4. Start All Services

From the project root, run:

```bash
docker compose up -d
```

This command will:
- Download all required Docker images
- Create persistent volumes for data storage
- Start all three services
- Enable GPU access for Ollama (if available)

### 5. Access the Services

Once started, the services will be available at:

- **Open WebUI**: [http://localhost:3000](http://localhost:3000)
- **Ollama API**: [http://localhost:11434](http://localhost:11434)
- **n8n**: [http://localhost:5678](http://localhost:5678)

### 6. Stopping the Services

To stop all services:

```bash
docker compose down
```

To stop and remove all data (including volumes):

```bash
docker compose down -v
```

---

## Service Details

### Ollama

Ollama is the core LLM inference engine that runs the language models locally.

**Configuration:**
- Port: `11434`
- GPU Access: Enabled (requires Nvidia Container Toolkit)
- Storage: Docker volume `ollama_data`

**Installing Models:**

See the full [Ollama documentation](https://ollama.com/) for all available models.

Chat model:
```bash
docker exec -it ollama ollama pull llama3.1:8b
```

Code model:
```bash
docker exec -it ollama ollama pull qwen2.5-coder:1.5b-base
```

Embedding model:
```bash
docker exec -it ollama ollama pull nomic-embed-text:latest
```

List installed models:
```bash
docker exec -it ollama ollama list
```

**Testing Ollama:**

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.1:8b",
  "prompt": "Hello, world!"
}'
```

---

### Open WebUI

Open WebUI provides a user-friendly web interface for interacting with your local LLMs.

**Configuration:**
- Port: `3000` (maps to internal port `8080`)
- Storage: Local directory `./open-webui` mapped to `/app/backend/data`

**Features:**
- Chat interface similar to ChatGPT
- Support for multiple models
- Conversation history
- Model management
- User authentication

**Documentation:**
- [Open WebUI GitHub](https://github.com/open-webui/open-webui)
- [Open WebUI Documentation](https://docs.openwebui.com/)

---

### n8n - Workflow Automation

n8n is a powerful workflow automation tool that allows you to create complex workflows and integrate your local LLMs into various automation scenarios.

**Configuration:**
- Port: `5678`
- Timezone: EST
- Storage: Docker volume `n8n_data` (persistent workflows and credentials)
- Runners: Enabled for executing workflows

**Features:**
- Visual workflow editor
- 300+ integrations
- LLM integration via HTTP requests to Ollama
- Webhook support
- Schedule-based automation
- Data transformation and processing

**Getting Started with n8n:**

1. Access n8n at [http://localhost:5678](http://localhost:5678)
2. Create an account (data is stored locally)
3. Create your first workflow
4. Use the HTTP Request node to connect to Ollama at `http://ollama:11434`

**Example n8n → Ollama Integration:**

In n8n, create an HTTP Request node with:
- Method: POST
- URL: `http://ollama:11434/api/generate`
- Body (JSON):
  ```json
  {
    "model": "llama3.1:8b",
    "prompt": "Your prompt here",
    "stream": false
  }
  ```

**Documentation:**
- [n8n Official Documentation](https://docs.n8n.io/)
- [n8n Community Forum](https://community.n8n.io/)

---

## Docker Compose Configuration

The complete `docker-compose.yml` configuration:

```yaml
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n
    container_name: n8n
    ports:
      - "5678:5678"
    environment:
      GENERIC_TIMEZONE: "EST"
      TZ: "EST"
      N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS: "true"
      N8N_RUNNERS_ENABLED: "true"
    volumes:
      - n8n_data:/home/node/.n8n
    restart: unless-stopped

  ollama:
    image: ollama/ollama
    container_name: ollama
    gpus: 'all'
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - '11434:11434'

  openui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    volumes:
      - ./open-webui:/app/backend/data
    ports:
      - 3000:8080

volumes:
  ollama_data:
  n8n_data:
```

---

## Troubleshooting

### General Issues

- **Services won't start**: Ensure Docker is running and you have sufficient system resources
- **Permission Errors**: On Linux/Mac, ensure your user has access to Docker and the mounted directories
- **Port conflicts**: Make sure ports 3000, 5678, and 11434 are not already in use

### Ollama Issues

- **GPU not detected**: Verify Nvidia Container Toolkit is properly installed
- **Models not loading**: Check available disk space and memory
- **Connection refused**: Ensure the Ollama container is running with `docker ps`

### Open WebUI Issues

- **Can't connect to Ollama**: Make sure Ollama is running and models are installed
- **Data not persisting**: Verify the `open-webui` directory exists and has proper permissions

### n8n Issues

- **Workflows not saving**: Check that the `n8n_data` volume has sufficient space
- **Can't connect to Ollama**: Use `http://ollama:11434` (Docker internal network) instead of `localhost`
- **Timezone issues**: Adjust the `GENERIC_TIMEZONE` and `TZ` environment variables in `docker-compose.yml`

### Checking Logs

View logs for specific services:

```bash
# All services
docker compose logs

# Specific service
docker compose logs ollama
docker compose logs open-webui
docker compose logs n8n

# Follow logs in real-time
docker compose logs -f
```

---

## Notes

- All data is persisted in Docker volumes or local directories and won't be lost when containers restart
- The `open-webui` directory stores user data, conversations, and settings
- Ollama models can be large (several GB each) - ensure sufficient disk space
- n8n workflows and credentials are stored in the `n8n_data` volume
- GPU support requires an Nvidia GPU and proper driver installation

---

## Additional Resources

- [Ollama Documentation](https://ollama.com/)
- [Ollama Model Library](https://ollama.com/library)
- [Open WebUI Documentation](https://docs.openwebui.com/)
- [Open WebUI GitHub](https://github.com/open-webui/open-webui)
- [n8n Documentation](https://docs.n8n.io/)
- [n8n Community](https://community.n8n.io/)
- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
