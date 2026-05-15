"""
title: n8n Pipe Function
author: Nick Ek
version: 0.6.0

This module defines a Pipe class that utilizes N8N for an Agent with streaming support
"""

from typing import Optional, Callable, Awaitable, AsyncGenerator
from pydantic import BaseModel, Field
import asyncio
import time
import aiohttp
import json


def extract_event_info(event_emitter) -> tuple[Optional[str], Optional[str]]:
    if not event_emitter or not event_emitter.__closure__:
        return None, None
    for cell in event_emitter.__closure__:
        if isinstance(request_info := cell.cell_contents, dict):
            chat_id = request_info.get("chat_id")
            message_id = request_info.get("message_id")
            return chat_id, message_id
    return None, None


async def emit_status(
    __event_emitter__: Callable[[dict], Awaitable[None]],
    level: str,
    message: str,
    done: bool,
    enable_status_indicator: bool,
    last_emit_time: float,
    emit_interval: float,
) -> float:
    """
    Stateless emit helper — takes and returns last_emit_time so
    no shared mutable state lives on the Pipe instance.
    """
    current_time = time.time()
    if (
        __event_emitter__
        and enable_status_indicator
        and (current_time - last_emit_time >= emit_interval or done)
    ):
        await __event_emitter__(
            {
                "type": "status",
                "data": {
                    "status": "complete" if done else "in_progress",
                    "level": level,
                    "description": message,
                    "done": done,
                },
            }
        )
        return current_time
    return last_emit_time


class Pipe:
    class Valves(BaseModel):
        n8n_url: str = Field(default="http://n8n:5678/webhook/invoke_n8n_agent")
        n8n_bearer_token: str = Field(default="...")
        input_field: str = Field(default="chatInput")
        response_field: str = Field(default="output")
        emit_interval: float = Field(
            default=2.0, description="Interval in seconds between status emissions"
        )
        enable_status_indicator: bool = Field(
            default=True, description="Enable or disable status indicator emissions"
        )
        request_timeout: float = Field(
            default=300.0, description="Timeout in seconds for n8n requests"
        )
        max_retries: int = Field(
            default=3,
            description="Maximum number of retry attempts on transient failures",
        )
        retry_base_delay: float = Field(
            default=1.0,
            description="Base delay in seconds for exponential backoff (delay = base * 2^attempt)",
        )
        retry_max_delay: float = Field(
            default=30.0, description="Maximum delay in seconds between retries"
        )
        enable_streaming: bool = Field(
            default=True, description="Enable streaming responses from n8n"
        )

    def __init__(self):
        self.type = "pipe"
        self.id = "n8n_pipe"
        self.name = "N8N Pipe"
        self.valves = self.Valves()
        # NOTE: No per-request mutable state on self.
        # Previously self.last_emit_time was here — that caused all concurrent
        # users to share the same emit timer, serialising their requests.

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Awaitable[None]] = None,
        __event_call__: Callable[[dict], Awaitable[dict]] = None,
    ) -> AsyncGenerator[str, None]:

        # Per-request emit time — lives on the stack, not on self
        last_emit_time: float = 0.0

        async def _emit(level: str, message: str, done: bool) -> None:
            """Thin wrapper so callers don't repeat all the valve args."""
            nonlocal last_emit_time
            last_emit_time = await emit_status(
                __event_emitter__,
                level,
                message,
                done,
                self.valves.enable_status_indicator,
                last_emit_time,
                self.valves.emit_interval,
            )

        await _emit("info", "Calling N8N Workflow...", False)

        chat_id, _ = extract_event_info(__event_emitter__)
        messages = body.get("messages", [])

        if not messages:
            await _emit("error", "No messages found in the request body", True)
            yield "No messages found in the request body"
            return

        question = messages[-1]["content"]

        headers = {
            "Authorization": f"Bearer {self.valves.n8n_bearer_token}",
            "Content-Type": "application/json",
        }
        payload = {"sessionId": str(chat_id)}
        payload[self.valves.input_field] = question

        # Streaming responses don't support retries once started
        # So we only retry on connection failures before streaming begins
        last_exception = None

        for attempt in range(self.valves.max_retries + 1):
            if attempt > 0:
                delay = min(
                    self.valves.retry_base_delay * (2 ** (attempt - 1)),
                    self.valves.retry_max_delay,
                )
                await _emit(
                    "info",
                    f"Retrying... (attempt {attempt}/{self.valves.max_retries}, waiting {delay:.0f}s)",
                    False,
                )
                await asyncio.sleep(delay)

            try:
                timeout = aiohttp.ClientTimeout(total=self.valves.request_timeout)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        self.valves.n8n_url, json=payload, headers=headers
                    ) as response:
                        if response.status != 200:
                            if response.status in (429, 502, 503, 504):
                                # Transient server-side errors — worth retrying
                                error_text = await response.text()
                                last_exception = Exception(
                                    f"Transient error: {response.status} - {error_text}"
                                )
                                continue
                            else:
                                # Non-retryable error
                                error_text = await response.text()
                                await _emit(
                                    "error",
                                    f"Non-retryable error: {response.status} - {error_text}",
                                    True,
                                )
                                yield f"Error: {response.status} - {error_text}"
                                return

                        # n8n streams in NDJSON format when streaming is enabled
                        if self.valves.enable_streaming:
                            # Handle NDJSON (newline-delimited JSON) streaming
                            await _emit("info", "Receiving streaming response...", False)
                            buffer = ""
                            items_yielded = 0

                            try:
                                async for chunk in response.content.iter_any():
                                    if not chunk:
                                        continue

                                    chunk_str = chunk.decode("utf-8")
                                    buffer += chunk_str

                                    # Process complete lines
                                    while "\n" in buffer:
                                        line, buffer = buffer.split("\n", 1)
                                        line = line.strip()

                                        if not line:
                                            continue

                                        try:
                                            data = json.loads(line)
                                            msg_type = data.get("type", "")

                                            if msg_type == "begin":
                                                continue
                                            elif msg_type == "item":
                                                content = data.get("content", "")
                                                if content:
                                                    # Check if content is itself a JSON string (final complete response)
                                                    try:
                                                        nested_data = json.loads(content)
                                                        # If it's JSON with response_field, it's the final complete response
                                                        if isinstance(nested_data, dict) and self.valves.response_field in nested_data:
                                                            # Only yield if we haven't streamed anything yet (fallback)
                                                            if items_yielded == 0:
                                                                nested_content = nested_data.get(self.valves.response_field, "")
                                                                if nested_content:
                                                                    items_yielded += 1
                                                                    yield nested_content
                                                        else:
                                                            # Not the expected format, yield the content as-is
                                                            items_yielded += 1
                                                            yield content
                                                    except (json.JSONDecodeError, TypeError):
                                                        # Not JSON, yield content as-is (streaming tokens)
                                                        items_yielded += 1
                                                        yield content
                                            elif msg_type == "end":
                                                # Don't break - process remaining items
                                                continue
                                            else:
                                                # Fallback: try response_field
                                                content = data.get(self.valves.response_field, "")
                                                if content:
                                                    items_yielded += 1
                                                    yield content

                                        except json.JSONDecodeError:
                                            # Treat as plain text if not JSON
                                            if line:
                                                items_yielded += 1
                                                yield line

                                # Process any remaining data
                                if buffer.strip():
                                    try:
                                        data = json.loads(buffer.strip())
                                        msg_type = data.get("type", "")

                                        if msg_type == "item":
                                            content = data.get("content", "")
                                            if content:
                                                # Check for nested JSON (final complete response)
                                                try:
                                                    nested_data = json.loads(content)
                                                    if isinstance(nested_data, dict) and self.valves.response_field in nested_data:
                                                        # Only yield if we haven't streamed anything yet
                                                        if items_yielded == 0:
                                                            nested_content = nested_data.get(self.valves.response_field, "")
                                                            if nested_content:
                                                                items_yielded += 1
                                                                yield nested_content
                                                    else:
                                                        items_yielded += 1
                                                        yield content
                                                except (json.JSONDecodeError, TypeError):
                                                    items_yielded += 1
                                                    yield content
                                        elif self.valves.response_field in data:
                                            content = data.get(self.valves.response_field, "")
                                            if content:
                                                items_yielded += 1
                                                yield content
                                    except json.JSONDecodeError:
                                        items_yielded += 1
                                        yield buffer.strip()

                            except Exception as e:
                                error_msg = f"Streaming error: {str(e)}"
                                await _emit("error", error_msg, True)
                                yield error_msg
                                return

                            await _emit("info", "Streaming complete", True)
                            return

                        else:
                            # Handle non-streaming response
                            await _emit("info", "Receiving non-streaming response...", False)
                            try:
                                raw_text = await response.text()

                                # Check if it's NDJSON (multiple JSON objects separated by newlines)
                                lines = raw_text.strip().split("\n")
                                if len(lines) > 1:
                                    # NDJSON format
                                    items_yielded = 0

                                    for line in lines:
                                        line = line.strip()
                                        if not line:
                                            continue

                                        try:
                                            data = json.loads(line)

                                            if isinstance(data, dict):
                                                msg_type = data.get("type", "")

                                                if msg_type == "begin":
                                                    continue
                                                elif msg_type == "item":
                                                    content = data.get("content", "")
                                                    if content:
                                                        # Check if content is itself a JSON string (final complete response)
                                                        try:
                                                            nested_data = json.loads(content)
                                                            if isinstance(nested_data, dict) and self.valves.response_field in nested_data:
                                                                # Only yield if we haven't streamed anything yet (fallback)
                                                                if items_yielded == 0:
                                                                    nested_content = nested_data.get(self.valves.response_field, "")
                                                                    if nested_content:
                                                                        items_yielded += 1
                                                                        yield nested_content
                                                            else:
                                                                items_yielded += 1
                                                                yield content
                                                        except (json.JSONDecodeError, TypeError):
                                                            items_yielded += 1
                                                            yield content
                                                elif msg_type == "end":
                                                    continue
                                                elif self.valves.response_field in data:
                                                    content = data.get(self.valves.response_field, "")
                                                    if content:
                                                        items_yielded += 1
                                                        yield content

                                        except json.JSONDecodeError:
                                            continue

                                    if items_yielded == 0:
                                        # No content was yielded, return raw response as fallback
                                        yield raw_text

                                    await _emit("info", "Complete", True)
                                    return

                                else:
                                    # Single JSON object
                                    response_json = json.loads(raw_text)
                                    n8n_response = response_json.get(
                                        self.valves.response_field, ""
                                    )
                                    await _emit("info", "Complete", True)
                                    yield n8n_response
                                    return

                            except json.JSONDecodeError as e:
                                error_msg = f"JSON parse error: {str(e)}"
                                await _emit("error", error_msg, True)
                                yield f"Error parsing response: {str(e)}"
                                return

            except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
                # Network-level transient failures — worth retrying
                last_exception = e

        # All retries exhausted
        error_msg = f"All {self.valves.max_retries} retries exhausted. Last error: {last_exception}"
        await _emit("error", error_msg, True)
        yield f"Error: {error_msg}"
