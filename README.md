# Tutor Agent

An agentic RAG (Retrieval-Augmented Generation) application that turns your Google Drive notes and documents into an interactive AI tutor. Documents are automatically ingested, chunked, and embedded into a Postgres vector database. A Claude-powered agent retrieves relevant content and supports multiple active-learning study modes through a chat interface.

---

## Architecture

```
Google Drive (source folder)
        │
        ▼
    n8n Workflow  ─────────────────────────────────────────────
    │                                                          │
    │  Ingestion Pipeline                                      │
    │  Google Drive → Download → Extract (PDF/Docs/Sheets/    │
    │  Excel) → Chunk → Embed (nomic-embed-text 768-dim) →    │
    │  Postgres (pgvector)                                     │
    │                                                          │
    │  AI Agent                                                │
    │  Chat webhook → Claude Sonnet → tools:                   │
    │    • RAG lookup (vector similarity search)               │
    │    • List documents (file metadata)                      │
    │    • Full document retrieval                             │
    │    • SQL queries on tabular data (document_rows)         │
    │    • Postgres chat memory (session history)              │
        │
        ▼
   Open WebUI  ←→  User (chat interface on port 3000)
        │
   n8n-pipe.py (custom pipe function with streaming + retry)
```

**Services:**

| Service | Port | Purpose |
|---------|------|---------|
| Open WebUI | 3000 | Chat frontend |
| n8n | 5678 | Workflow orchestrator |
| Ollama | 11434 | Local embedding model |
| Postgres | 5432 | Vector store + app databases |

---

## Prerequisites

- [Docker](https://docs.docker.com/engine/install/) and [Docker Compose](https://docs.docker.com/compose/install/)
- [Nvidia Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (GPU required for Ollama)
- Linux OS
- An [Anthropic API key](https://console.anthropic.com/)
- A Google Cloud project with Drive API enabled and OAuth2 credentials (for n8n)

---

## Quick Start

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd tutor_agent
cp .env.example .env
```

Edit `.env` and fill in all required values — see [Environment Variables](#environment-variables) below.

### 2. Start all services

```bash
./run_local.sh --fresh
```

`--fresh` tears down any existing containers and volumes, rebuilds images, starts all services, and runs the initialization scripts that configure n8n and Open WebUI automatically.

After `--fresh` completes, services are available at:
- **Open WebUI**: http://localhost:3000
- **n8n**: http://localhost:5678
- **Ollama**: http://localhost:11434

### 3. Pull the embedding model

```bash
docker exec -it ollama ollama pull nomic-embed-text:latest
```

### 4. Set up n8n credentials

In n8n (http://localhost:5678), configure:
- **Google Drive OAuth2** — used by the Drive trigger and download nodes
- **Anthropic API** — your API key for Claude
- **Postgres** — points to the `postgres-tutor` container (host: `postgres`, port: `5432`)
- **Supabase** — same Postgres instance, used for the vector store nodes

### 5. Create the database tables

The workflow includes a one-time setup section. In n8n, open the **Tutor Agent** workflow and manually execute the three setup nodes (labeled **"Run Each Node Once to Set Up Database Tables"**):

1. `Create Documents Table and Match Function` — creates the `documents` table with pgvector and the `match_documents()` similarity search function
2. `Create Document Metadata Table` — creates the `document_metadata` table
3. `Create Document Rows Table` — creates the `document_rows` table for tabular data

Run each node once by clicking **Execute Node** on each individually.

### 6. Activate the workflow

Enable the Tutor Agent workflow in n8n. Once active, it listens for:
- New or updated files in your configured Google Drive folder
- Chat messages from Open WebUI via webhook

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values below.

### n8n

| Variable | Description |
|----------|-------------|
| `N8N_PORT` | n8n port (default: `5678`) |
| `N8N_OWNER_EMAIL` | Admin account email |
| `N8N_OWNER_FIRST_NAME` | Admin first name |
| `N8N_OWNER_LAST_NAME` | Admin last name |
| `N8N_OWNER_PASSWORD` | Admin password |
| `N8N_ENCRYPTION_KEY` | Auto-generated on `--fresh` start |

### Open WebUI

| Variable | Description |
|----------|-------------|
| `WEBUI_PORT` | UI port (default: `3000`) |
| `WEBUI_ADMIN_EMAIL` | Admin account email |
| `WEBUI_ADMIN_PASSWORD` | Admin password |
| `WEBUI_SECRET_KEY` | Auto-generated on `--fresh` start |

### Postgres

| Variable | Description |
|----------|-------------|
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `POSTGRES_HOST` | `postgres` (Docker service name) |
| `POSTGRES_PORT` | `5432` |

---

## Workflow Overview

The n8n workflow (`apps/n8n/workflows/Tutor_Agent.json`) has three logical sections:

### Ingestion Pipeline (runs automatically on Drive events)

1. Google Drive Trigger detects new or updated files in the configured folder
2. Files are downloaded and routed by type: PDF, Google Docs, Google Sheets, Excel
3. Text is extracted and chunked via LangChain's Character Text Splitter
4. Chunks are embedded with `nomic-embed-text` (768 dimensions) via Ollama
5. Embeddings are stored in the `documents` Postgres table with file metadata

### AI Agent (runs on each chat message)

The LangChain agent (Claude Sonnet) receives messages from Open WebUI and selects from four tools:

- **RAG lookup** — cosine similarity search over the vector store
- **List documents** — shows the user what files are available
- **Get file contents** — fetches the full text of a specific document
- **Query document rows** — runs SQL against the `document_rows` table for spreadsheet data

Conversation history is persisted per session in Postgres.

### Database Setup (manual, run once)

Three disconnected nodes that create the Postgres schema. Execute each once during initial setup — see Step 5 above.

---

## Google Drive Configuration

The workflow monitors a specific folder by ID. To change the source folder:

1. Open the Tutor Agent workflow in n8n
2. Edit both Google Drive Trigger nodes (`File Created` and `File Updated`)
3. Update the **Folder ID** to your target folder

Supported file types: Google Docs, Google Sheets, PDF, Excel (`.xlsx`)

---

## Tutor Agent Study Modes

When chatting in Open WebUI, the agent will ask for your topic and preferred study mode:

| Mode | Description |
|------|-------------|
| **Flashcards** | Interactive HTML flashcard widgets with flip animation and progress tracking |
| **Mock Q&A** | Graded questions with source attribution |
| **Active Recall** | You explain concepts; the agent probes your understanding |
| **Feynman Mode** | Teach-back with naive follow-up questions |
| **Concept Map** | Cross-document synthesis and relationship mapping |
| **Cloze Deletion** | Fill-in-the-blank from your source material |
| **Custom** | User-defined study format |

The system prompt is in `agent/tutor-agent-system-prompt.md`.

---

## Database Management

### Reset the database

A standalone Postgres node in the workflow (labeled **"Reset Database"**) drops and recreates the schema. Execute it manually in n8n when you want to clear all ingested documents and start fresh. After resetting, re-run the three setup nodes to recreate the tables.

### Checking ingested documents

Connect to Postgres and query directly:

```bash
docker exec -it postgres-tutor psql -U <POSTGRES_USER> -d postgres
```

```sql
-- List all ingested files
SELECT title, url, created_at FROM document_metadata;

-- Check vector count
SELECT COUNT(*) FROM documents;
```

---

## Run Script Reference

```bash
./run_local.sh --fresh   # Rebuild everything from scratch (destroys all data)
./run_local.sh --up      # Start existing containers
./run_local.sh --down    # Stop containers (data preserved)
```

---

## Troubleshooting

**Services won't start**
- Ensure Docker is running: `docker info`
- Check ports 3000, 5678, 11434, and 5432 are free

**n8n can't connect to Postgres**
- Use `postgres` as the host (Docker service name), not `localhost`
- Verify credentials match your `.env` file

**Embeddings failing**
- Confirm `nomic-embed-text:latest` is pulled: `docker exec -it ollama ollama list`
- Check Ollama logs: `docker compose logs ollama`

**Google Drive trigger not firing**
- Verify the OAuth2 credentials are configured and authorized in n8n
- Confirm the folder ID in both trigger nodes matches your Drive folder

**Chat returns no results**
- Ensure the workflow is active and database tables exist (Step 5)
- Check that documents have been ingested: query `document_metadata`
- Review n8n execution logs for the AI Agent node

**Viewing logs**

```bash
docker compose logs -f            # all services
docker compose logs -f n8n        # n8n only
docker compose logs -f open-webui # Open WebUI only
docker compose logs -f ollama     # Ollama only
```

---

## Project Structure

```
tutor_agent/
├── docker-compose.yml          # Service definitions
├── run_local.sh                # Start/stop helper script
├── .env.example                # Environment variable template
├── init.sql                    # Creates openwebui and n8n databases
├── init_n8n.sh                 # Imports and publishes n8n workflow on first run
├── init_webui.sh               # Installs the n8n pipe function in Open WebUI
├── agent/
│   └── tutor-agent-system-prompt.md  # Agent personality and study mode logic
└── apps/
    ├── n8n/
    │   ├── Dockerfile
    │   └── workflows/
    │       └── Tutor_Agent.json      # Main RAG + agent workflow
    └── open-webui/
        ├── Dockerfile
        ├── n8n-pipe.py               # Open WebUI → n8n streaming pipe
        ├── functions/
        │   └── n8n-pipe.json         # Pipe function config
        └── tools/
            └── query_knowledgebase.py
```

---

## Resources

- [n8n Documentation](https://docs.n8n.io/)
- [Open WebUI Documentation](https://docs.openwebui.com/)
- [Ollama Model Library](https://ollama.com/library)
- [Anthropic API](https://docs.anthropic.com/)
- [pgvector](https://github.com/pgvector/pgvector)
