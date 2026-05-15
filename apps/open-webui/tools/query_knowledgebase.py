"""
title: Knowledge Base Search
author: nick
version: 0.2.0
description: Agentic RAG tool that lets the LLM decide when to query an OpenWebUI knowledge collection. Accepts kb_id as a configurable parameter so the same tool can target different knowledge bases.
requirements: requests, pydantic
"""

from typing import Callable, Awaitable, Optional
from pydantic import BaseModel, Field
import requests
import json


class Tools:
    class Valves(BaseModel):
        """
        Admin-level configuration. Set these in the Tool's settings panel
        in OpenWebUI. These are shared across all users of the tool.
        """

        openwebui_base_url: str = Field(
            default="http://localhost:8080",
            description="Base URL of the OpenWebUI instance. Use http://host.docker.internal:8080 if Ollama and OpenWebUI are in separate containers.",
        )
        api_key: str = Field(
            default="",
            description="OpenWebUI API key. Generate one in Settings → Account → API Keys.",
        )
        default_kb_id: str = Field(
            default="",
            description="Fallback knowledge base UUID if the model does not specify one. Find this in the URL when viewing a knowledge collection.",
        )
        top_k: int = Field(
            default=5,
            description="Maximum number of passages to return per query.",
        )
        debug: bool = Field(
            default=False,
            description="If true, emit verbose status messages to the chat.",
        )

    class UserValves(BaseModel):
        """
        Per-user overrides. Users can set their own kb_id here if they
        want this tool to default to their personal collection.
        """

        kb_id_override: str = Field(
            default="",
            description="Override the default knowledge base UUID for this user.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.user_valves = self.UserValves()
        # Show citations in the OpenWebUI chat UI when this tool returns results.
        self.citation = True

    async def search_knowledge_base(
        self,
        query: str,
        kb_id: Optional[str] = None,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> str:
        """
        Search a user's knowledge base for passages relevant to a query.

        Use this tool when the user asks a substantive question about
        their study materials, requests flashcards or Q&A on a topic,
        or needs you to verify a definition or specific fact from their
        documents. Do NOT call this for conversational replies like
        "yes", "more", "next", or mode-selection turns.

        Reformulate the user's message into a focused query before calling.
        Strip conversational filler. Include the key terms and concepts.

        :param query: A focused search query. Example: "Massachusetts loan
            officer licensing continuing education hours" — NOT "tell me
            more about that licensing thing we were discussing".
        :param kb_id: Optional knowledge base UUID. If omitted, uses the
            user's configured override, then the admin default.
        :return: A formatted string containing the top relevant passages,
            with source attribution for each.
        """

        # Resolve which knowledge base to query.
        # Priority: explicit arg → per-user valve → admin default valve.
        resolved_kb_id = (
            kb_id
            or self.user_valves.kb_id_override
            or self.valves.default_kb_id
        )

        if not resolved_kb_id:
            return (
                "ERROR: No knowledge base ID was provided and no default "
                "is configured. Ask the user which collection to search, "
                "or set default_kb_id in the tool's admin valves."
            )

        if not self.valves.api_key:
            return (
                "ERROR: OpenWebUI API key not configured. Set it in the "
                "tool's admin valves."
            )

        # Emit a status event so the user sees what's happening in the UI.
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Searching knowledge base for: {query}",
                        "done": False,
                    },
                }
            )

        url = f"{self.valves.openwebui_base_url.rstrip('/')}/api/v1/retrieval/query/collection"
        headers = {
            "Authorization": f"Bearer {self.valves.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "collection_names": [resolved_kb_id],
            "query": query,
            "k": self.valves.top_k,
        }

        if self.valves.debug and __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"POST {url} | kb_id={resolved_kb_id} | k={self.valves.top_k}",
                        "done": False,
                    },
                }
            )

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as e:
            return f"ERROR: Knowledge base request failed with HTTP {e.response.status_code}: {e.response.text}"
        except requests.exceptions.Timeout:
            return "ERROR: Knowledge base request timed out after 30 seconds."
        except Exception as e:
            return f"ERROR: Knowledge base request failed: {type(e).__name__}: {str(e)}"

        # OpenWebUI's retrieval response shape: documents are nested as
        # lists-of-lists when multiple collections are queried.
        documents = data.get("documents", [[]])
        metadatas = data.get("metadatas", [[]])

        # Flatten one level (we only queried one collection).
        if documents and isinstance(documents[0], list):
            documents = documents[0]
        if metadatas and isinstance(metadatas[0], list):
            metadatas = metadatas[0]

        if not documents:
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {
                            "description": "No relevant passages found.",
                            "done": True,
                        },
                    }
                )
            return (
                f"No passages in the knowledge base matched the query: '{query}'. "
                "Tell the user this material doesn't appear to be in their "
                "study set, and ask if they want to search differently or "
                "use general knowledge."
            )

        # Format results for the model. Include source metadata so the
        # model can cite documents back to the user.
        formatted = []
        for i, doc in enumerate(documents):
            meta = metadatas[i] if i < len(metadatas) else {}
            source = meta.get("name") or meta.get("source") or "unknown source"
            page = meta.get("page")
            source_label = f"{source}" + (f" (page {page})" if page is not None else "")
            formatted.append(f"[Passage {i+1} — {source_label}]\n{doc}")

        result = "\n\n---\n\n".join(formatted)

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Retrieved {len(documents)} passages.",
                        "done": True,
                    },
                }
            )

        return result

    async def list_available_knowledge_bases(
        self,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> str:
        """
        List all knowledge bases the user has access to, with their IDs
        and names. Use this if the user asks what's available, or if
        you need to look up a kb_id by collection name.
        """

        if not self.valves.api_key:
            return "ERROR: OpenWebUI API key not configured."

        url = f"{self.valves.openwebui_base_url.rstrip('/')}/api/v1/knowledge/"
        headers = {"Authorization": f"Bearer {self.valves.api_key}"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            collections = response.json()
        except Exception as e:
            return f"ERROR listing knowledge bases: {type(e).__name__}: {str(e)}"

        if not collections:
            return "No knowledge bases found."

        lines = ["Available knowledge bases:"]
        for kb in collections:
            kb_id = kb.get("id", "?")
            name = kb.get("name", "unnamed")
            desc = kb.get("description", "")
            lines.append(f"- {name} (id: {kb_id}){' — ' + desc if desc else ''}")

        return "\n".join(lines)