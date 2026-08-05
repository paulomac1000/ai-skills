#!/usr/bin/env python3
"""Generate a runnable, production-shaped Python MCP server baseline."""

from __future__ import annotations

import argparse
import ctypes
import errno
import keyword
import os
import re
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path

PACKAGE_RE = re.compile(r"[a-z][a-z0-9_]{1,62}$")
SERVER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{1,78}$")
RESERVED_PACKAGE_NAMES = frozenset(sys.stdlib_module_names) | {"mcp", "uvicorn", "pytest"}
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 0x00000004


def _clean(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n").rstrip() + "\n"


def _render(text: str, *, package: str, server_name: str) -> str:
    return _clean(text).replace("__PACKAGE__", package).replace("__SERVER_NAME__", server_name)


def project_files(package: str, server_name: str) -> dict[str, str]:
    """Return a complete generated project as relative UTF-8 text files."""
    if not PACKAGE_RE.fullmatch(package) or keyword.iskeyword(package) or package in RESERVED_PACKAGE_NAMES:
        raise ValueError("package must be a non-keyword, non-reserved import name matching [a-z][a-z0-9_]{1,62}")
    if not SERVER_RE.fullmatch(server_name):
        raise ValueError("server name must be 2-79 safe display characters")

    def render(text: str) -> str:
        return _render(text, package=package, server_name=server_name)

    return {
        "pyproject.toml": render(
            """
            [build-system]
            requires = ["setuptools>=75", "wheel"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "__PACKAGE__"
            version = "0.1.0"
            description = "Production-shaped MCP server generated from the MCP server architect standard"
            requires-python = ">=3.12"
            dependencies = ["mcp>=2.0.0,<3", "uvicorn>=0.30,<1"]

            [project.optional-dependencies]
            dev = ["pytest==9.0.2"]

            [project.scripts]
            __PACKAGE__ = "__PACKAGE__.server:main"

            [tool.setuptools.packages.find]
            where = ["src"]

            [tool.pytest.ini_options]
            testpaths = ["tests"]
            addopts = "-q"
            """
        ),
        "README.md": render(
            """
            # __SERVER_NAME__

            Generated production baseline for an MCP server. It separates domain code,
            capability manifests, one invocation kernel, SDK registration, and transports.

            ## Run

            ```bash
            python -m venv .venv
            . .venv/bin/activate
            pip install -e ".[dev]"
            __PACKAGE__
            ```

            Stdio is the default. For loopback Streamable HTTP:

            ```bash
            MCP_TRANSPORT=streamable-http MCP_HOST=127.0.0.1 MCP_PORT=8000 __PACKAGE__
            ```

            The HTTP path is `/mcp`. Only literal IPv4 or IPv6 loopback addresses are
            accepted. The ASGI boundary buffers at most the configured request limit and
            rejects oversized or excessively fragmented bodies before entering the MCP SDK application.

            Writes are disabled by default. A write requires a mandatory current version
            and a one-time approval token issued earlier by a trusted host. Approval records
            are bounded, expiring, and bound to capability, principal, target, and resource.
            The MCP tool cannot issue approval and a caller-provided boolean is never consent.

            Before production, replace the in-memory adapter, review every manifest, add
            authenticated principal extraction and resource-scoped authorization, connect
            approvals to a trusted UI or transport, add upstream contract tests, and test
            the exact built wheel or container.
            """
        ),
        "SECURITY.md": _clean(
            """
            # Security model

            The generated project is local-first. Stdio and literal-loopback-only
            Streamable HTTP are supported. Writes are disabled unless the operator enables
            them. A mutation additionally requires an exact optimistic-concurrency version
            and a one-time opaque approval token that already exists server-side.

            Only a trusted host, UI, or transport may issue approvals. Tokens are bounded,
            expiring, principal-, capability-, target-, resource-, and single-use-bound.
            Treat them as credentials and never log, trace, cache, or echo them.

            Before remote or multi-user deployment, add authentication, per-resource
            authorization, TLS or a reviewed proxy, Origin and Host policy, quotas, and
            deployment-specific secret storage.
            """
        ),
        ".env.example": _clean(
            """
            MCP_TRANSPORT=stdio
            MCP_HOST=127.0.0.1
            MCP_PORT=8000
            MCP_WRITE_ENABLED=false
            MCP_DEFAULT_DEADLINE_MS=10000
            MCP_MAX_RESULT_ITEMS=100
            MCP_MAX_REQUEST_BODY_BYTES=1048576
            """
        ),
        ".gitignore": _clean(
            """
            .env
            .venv/
            __pycache__/
            .pytest_cache/
            *.pyc
            build/
            dist/
            *.egg-info/
            """
        ),
        "Dockerfile": render(
            """
            FROM python:3.12-slim
            WORKDIR /app
            RUN useradd --create-home --uid 10001 appuser
            COPY pyproject.toml README.md ./
            COPY src ./src
            RUN pip install --no-cache-dir .
            USER appuser
            ENV MCP_TRANSPORT=stdio
            ENTRYPOINT ["__PACKAGE__"]
            """
        ),
        ".github/workflows/ci.yml": _clean(
            """
            name: CI

            on:
              pull_request:
              push:
                branches: [main]

            permissions:
              contents: read

            jobs:
              test:
                runs-on: ubuntu-latest
                timeout-minutes: 10
                steps:
                  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
                    with:
                      persist-credentials: false
                  - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
                    with:
                      python-version: "3.12"
                      cache: pip
                      cache-dependency-path: pyproject.toml
                  - run: python -m pip install -e ".[dev]"
                  - run: python -m compileall -q src tests
                  - run: python -m pytest
            """
        ),
        f"src/{package}/__init__.py": _clean(
            '''
            """Generated MCP server package."""
            __all__ = ["__version__"]
            __version__ = "0.1.0"
            '''
        ),
        f"src/{package}/__main__.py": render(
            """
            from __PACKAGE__.server import main

            if __name__ == "__main__":
                main()
            """
        ),
        f"src/{package}/config.py": render(
            '''
            """Typed immutable process configuration loaded before dependency construction."""

            from __future__ import annotations

            import ipaddress
            import os
            from dataclasses import dataclass
            from typing import Literal

            Transport = Literal["stdio", "streamable-http"]

            def _boolean(name: str, default: bool) -> bool:
                raw = os.getenv(name)
                if raw is None:
                    return default
                value = raw.strip().casefold()
                if value in {"1", "true", "yes", "on"}:
                    return True
                if value in {"0", "false", "no", "off"}:
                    return False
                raise ValueError(f"{name} must be a boolean")

            def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
                raw = os.getenv(name)
                try:
                    value = default if raw is None else int(raw)
                except ValueError as exc:
                    raise ValueError(f"{name} must be an integer") from exc
                if not minimum <= value <= maximum:
                    raise ValueError(f"{name} must be between {minimum} and {maximum}")
                return value

            def _require_literal_loopback(host: str) -> None:
                try:
                    address = ipaddress.ip_address(host)
                except ValueError as exc:
                    raise ValueError("MCP_HOST must be a literal IPv4 or IPv6 loopback address") from exc
                if not address.is_loopback:
                    raise ValueError("Generated baseline refuses non-loopback HTTP binding")

            @dataclass(frozen=True, slots=True)
            class Settings:
                transport: Transport = "stdio"
                host: str = "127.0.0.1"
                port: int = 8000
                write_enabled: bool = False
                default_deadline_ms: int = 10_000
                max_result_items: int = 100
                max_request_body_bytes: int = 1_048_576

                def validate(self) -> "Settings":
                    if not isinstance(self.transport, str) or self.transport not in {"stdio", "streamable-http"}:
                        raise ValueError("transport must be stdio or streamable-http")
                    if not isinstance(self.host, str) or not self.host:
                        raise ValueError("host must be a non-empty string")
                    if type(self.write_enabled) is not bool:
                        raise ValueError("write_enabled must be a boolean")
                    if self.transport == "streamable-http":
                        _require_literal_loopback(self.host)
                    if type(self.port) is not int or not 1 <= self.port <= 65_535:
                        raise ValueError("port must be between 1 and 65535")
                    if type(self.default_deadline_ms) is not int or not 100 <= self.default_deadline_ms <= 120_000:
                        raise ValueError("default_deadline_ms must be between 100 and 120000")
                    if type(self.max_result_items) is not int or not 1 <= self.max_result_items <= 1_000:
                        raise ValueError("max_result_items must be between 1 and 1000")
                    if type(self.max_request_body_bytes) is not int or not 1_024 <= self.max_request_body_bytes <= 16_777_216:
                        raise ValueError("max_request_body_bytes must be between 1024 and 16777216")
                    return self

                @classmethod
                def from_env(cls) -> "Settings":
                    return cls(
                        transport=os.getenv("MCP_TRANSPORT", "stdio").strip().casefold(),  # type: ignore[arg-type]
                        host=os.getenv("MCP_HOST", "127.0.0.1").strip(),
                        port=_integer("MCP_PORT", 8000, 1, 65_535),
                        write_enabled=_boolean("MCP_WRITE_ENABLED", False),
                        default_deadline_ms=_integer("MCP_DEFAULT_DEADLINE_MS", 10_000, 100, 120_000),
                        max_result_items=_integer("MCP_MAX_RESULT_ITEMS", 100, 1, 1_000),
                        max_request_body_bytes=_integer("MCP_MAX_REQUEST_BODY_BYTES", 1_048_576, 1_024, 16_777_216),
                    ).validate()
            '''
        ),
        f"src/{package}/manifests.py": render(
            '''
            """Application-owned capability manifests; missing metadata is a startup error."""

            from dataclasses import asdict, dataclass
            from typing import Literal

            SideEffects = Literal["read", "write", "destructive"]
            Confidentiality = Literal["public", "internal", "personal", "sensitive", "credential"]

            @dataclass(frozen=True, slots=True)
            class CapabilityManifest:
                name: str
                version: str
                side_effects: SideEffects
                confidentiality: Confidentiality
                operational_impact: str
                cost: str
                reversible: bool
                idempotent: bool
                idempotency_mechanism: str | None
                retryable: bool
                retry_conditions: tuple[str, ...]
                concurrent_safe: bool
                concurrency_scope: str
                timeout_ms: int
                requires_confirmation: bool
                target_binding: str
                active: bool = True

                def as_dict(self) -> dict[str, object]:
                    return asdict(self)

            def _read(name: str, confidentiality: Confidentiality, target: str) -> CapabilityManifest:
                return CapabilityManifest(
                    name, "1.0.0", "read", confidentiality, "none", "cheap", True,
                    True, "natural read", False, (), True, "none", 5_000, False, target,
                )

            MANIFESTS = {
                "describe_capabilities": _read("describe_capabilities", "public", "capability catalog"),
                "get_health": _read("get_health", "internal", "process runtime"),
                "list_items": _read("list_items", "internal", "process inventory"),
                "put_item": CapabilityManifest(
                    "put_item", "1.0.0", "write", "internal", "persistent", "cheap",
                    True, False, None, False, (), False, "inventory item", 5_000, True,
                    "stable item_id plus mandatory expected_version",
                ),
            }

            def validate_manifests(registered_names: set[str]) -> None:
                missing = registered_names - set(MANIFESTS)
                orphaned = set(MANIFESTS) - registered_names
                if missing or orphaned:
                    raise RuntimeError(f"manifest coverage mismatch: missing={sorted(missing)}, orphaned={sorted(orphaned)}")
                for manifest in MANIFESTS.values():
                    if manifest.timeout_ms <= 0:
                        raise RuntimeError(f"invalid timeout for {manifest.name}")
                    if manifest.retryable and not manifest.idempotent:
                        raise RuntimeError(f"retryable capability lacks idempotency proof: {manifest.name}")
                    if manifest.side_effects != "read" and manifest.retryable:
                        raise RuntimeError(f"generated writes must default to non-retryable: {manifest.name}")
            '''
        ),
        f"src/{package}/domain.py": render(
            '''
            """Transport-independent domain service and deterministic in-memory adapter."""

            import asyncio
            from dataclasses import asdict, dataclass

            class ConflictError(Exception):
                """The caller used a stale resource version."""

            @dataclass(frozen=True, slots=True)
            class Item:
                item_id: str
                name: str
                version: int
                def as_dict(self) -> dict[str, object]:
                    return asdict(self)

            class InventoryService:
                def __init__(self) -> None:
                    self._items = {"example": Item("example", "Example item", 1)}
                    self._lock = asyncio.Lock()

                async def list_items(self, limit: int) -> list[Item]:
                    if type(limit) is not int or not 1 <= limit <= 1_000:
                        raise ValueError("limit must be an integer between 1 and 1000")
                    return sorted(self._items.values(), key=lambda item: item.item_id)[:limit]

                async def put_item(self, item_id: str, name: str, expected_version: int) -> Item:
                    if not isinstance(item_id, str) or not item_id or len(item_id) > 64:
                        raise ValueError("item_id must contain 1-64 characters")
                    if not isinstance(name, str) or not name.strip() or len(name) > 200:
                        raise ValueError("name must contain 1-200 characters")
                    if type(expected_version) is not int or expected_version < 0:
                        raise ValueError("expected_version is mandatory and must be a non-negative integer")
                    async with self._lock:
                        current = self._items.get(item_id)
                        version = current.version if current else 0
                        if expected_version != version:
                            raise ConflictError(f"stale expected_version={expected_version}; current_version={version}")
                        updated = Item(item_id, name.strip(), version + 1)
                        self._items[item_id] = updated
                        return updated
            '''
        ),
        f"src/{package}/kernel.py": render(
            '''
            """Single invocation kernel shared by MCP and any future adapters."""

            import asyncio
            import contextvars
            import secrets
            import threading
            import time
            import uuid
            from collections.abc import Awaitable, Callable
            from dataclasses import dataclass
            from typing import Any

            from __PACKAGE__.config import Settings
            from __PACKAGE__.domain import ConflictError, InventoryService
            from __PACKAGE__.manifests import MANIFESTS, CapabilityManifest

            _request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

            @dataclass(frozen=True, slots=True)
            class CallerContext:
                principal: str = "local-stdio-user"
                target_id: str = "inventory"
                approval_token: str | None = None

            @dataclass(frozen=True, slots=True)
            class ApprovalRecord:
                capability: str
                principal: str
                target_id: str
                resource_id: str
                expires_at: float

            class ApprovalRegistry:
                """Bounded one-time approvals issued only by a trusted embedding host or UI."""
                def __init__(self, max_records: int = 1_024) -> None:
                    if type(max_records) is not int or not 1 <= max_records <= 10_000:
                        raise ValueError("max_records must be an integer between 1 and 10000")
                    self._max_records = max_records
                    self._records: dict[str, ApprovalRecord] = {}
                    self._lock = threading.Lock()

                def _purge_expired_locked(self, now: float) -> None:
                    for token in [token for token, record in self._records.items() if record.expires_at < now]:
                        self._records.pop(token, None)

                def issue(self, capability: str, principal: str, target_id: str, resource_id: str, *, ttl_seconds: float = 60.0) -> str:
                    if not all(isinstance(value, str) and value for value in (capability, principal, target_id, resource_id)):
                        raise ValueError("approval binding values must be non-empty strings")
                    if not isinstance(ttl_seconds, (int, float)) or isinstance(ttl_seconds, bool) or not 0 < ttl_seconds <= 300:
                        raise ValueError("approval ttl must be numeric and between 0 and 300 seconds")
                    now = time.monotonic()
                    with self._lock:
                        self._purge_expired_locked(now)
                        if len(self._records) >= self._max_records:
                            raise RuntimeError("approval registry capacity reached")
                        token = secrets.token_urlsafe(32)
                        while token in self._records:
                            token = secrets.token_urlsafe(32)
                        self._records[token] = ApprovalRecord(capability, principal, target_id, resource_id, now + float(ttl_seconds))
                        return token

                def consume(self, token: str | None, capability: str, principal: str, target_id: str, resource_id: str) -> bool:
                    if not isinstance(token, str) or not token:
                        return False
                    now = time.monotonic()
                    with self._lock:
                        self._purge_expired_locked(now)
                        record = self._records.pop(token, None)
                    return record is not None and record.capability == capability and record.principal == principal and record.target_id == target_id and record.resource_id == resource_id

            class InvocationKernel:
                def __init__(self, settings: Settings, service: InventoryService, approvals: ApprovalRegistry | None = None) -> None:
                    self._settings = settings.validate()
                    self._service = service
                    self._approvals = approvals or ApprovalRegistry()
                    self._locks: dict[str, asyncio.Lock] = {}
                    self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[Any]]] = {
                        "describe_capabilities": self._describe_capabilities,
                        "get_health": self._get_health,
                        "list_items": self._list_items,
                        "put_item": self._put_item,
                    }

                @property
                def active_names(self) -> set[str]:
                    return {name for name, manifest in MANIFESTS.items() if manifest.active}

                def catalog(self) -> list[dict[str, object]]:
                    return [MANIFESTS[name].as_dict() for name in sorted(self.active_names)]

                async def invoke(self, name: str, arguments: dict[str, Any], caller: CallerContext | None = None) -> dict[str, Any]:
                    caller = caller or CallerContext()
                    request_id = uuid.uuid4().hex
                    context_token = _request_id.set(request_id)
                    started = time.monotonic()
                    try:
                        manifest = self._manifest(name)
                        self._validate_arguments(name, arguments)
                        self._authorize(name, manifest, caller, arguments)
                        seconds = min(manifest.timeout_ms, self._settings.default_deadline_ms) / 1000
                        lock = self._lock_for(manifest, arguments)
                        async with asyncio.timeout(seconds):
                            if lock is None:
                                data = await self._handlers[name](arguments)
                            else:
                                async with lock:
                                    data = await self._handlers[name](arguments)
                        return {"success": True, "data": data, "_meta": {"request_id": request_id, "target_id": caller.target_id, "duration_ms": int((time.monotonic() - started) * 1000)}}
                    except ValueError as exc:
                        return self._failure("VALIDATION_FAILED", str(exc), request_id, started)
                    except ConflictError as exc:
                        return self._failure("CONFLICT", str(exc), request_id, started)
                    except PermissionError as exc:
                        return self._failure("AUTHORIZATION_FAILED", str(exc), request_id, started)
                    except TimeoutError:
                        return self._failure("TIMEOUT", "operation deadline exceeded", request_id, started)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        return self._failure("INTERNAL_ERROR", "internal operation failure", request_id, started)
                    finally:
                        _request_id.reset(context_token)

                def _manifest(self, name: str) -> CapabilityManifest:
                    manifest = MANIFESTS.get(name)
                    if manifest is None or not manifest.active or name not in self._handlers:
                        raise ValueError(f"unknown or inactive capability: {name}")
                    return manifest

                @staticmethod
                def _validate_arguments(name: str, arguments: dict[str, Any]) -> None:
                    if not isinstance(arguments, dict):
                        raise ValueError("arguments must be an object")
                    if name == "list_items":
                        limit = arguments.get("limit", 25)
                        if type(limit) is not int or not 1 <= limit <= 1_000:
                            raise ValueError("limit must be an integer between 1 and 1000")
                    if name == "put_item":
                        item_id, item_name = arguments.get("item_id"), arguments.get("name")
                        expected_version = arguments.get("expected_version")
                        if not isinstance(item_id, str) or not item_id or len(item_id) > 64:
                            raise ValueError("item_id must contain 1-64 characters")
                        if not isinstance(item_name, str) or not item_name.strip() or len(item_name) > 200:
                            raise ValueError("name must contain 1-200 characters")
                        if type(expected_version) is not int or expected_version < 0:
                            raise ValueError("expected_version is mandatory and must be a non-negative integer")

                def _authorize(self, name: str, manifest: CapabilityManifest, caller: CallerContext, arguments: dict[str, Any]) -> None:
                    if not isinstance(caller.principal, str) or not caller.principal:
                        raise PermissionError("principal is not authenticated")
                    if caller.target_id != "inventory":
                        raise PermissionError("target is not authorized")
                    if manifest.side_effects == "read":
                        return
                    if not self._settings.write_enabled:
                        raise PermissionError("write operations are disabled by operator policy")
                    if manifest.requires_confirmation and not self._approvals.consume(
                        caller.approval_token, name, caller.principal, caller.target_id, str(arguments["item_id"])
                    ):
                        raise PermissionError("a valid one-time server-side approval record is required")

                def _lock_for(self, manifest: CapabilityManifest, arguments: dict[str, Any]) -> asyncio.Lock | None:
                    if manifest.concurrent_safe:
                        return None
                    return self._locks.setdefault(str(arguments.get("item_id") or manifest.concurrency_scope), asyncio.Lock())

                async def _describe_capabilities(self, _arguments: dict[str, Any]) -> list[dict[str, object]]:
                    return self.catalog()

                async def _get_health(self, _arguments: dict[str, Any]) -> dict[str, object]:
                    return {"ready": True, "active_capabilities": len(self.active_names), "write_enabled": self._settings.write_enabled}

                async def _list_items(self, arguments: dict[str, Any]) -> list[dict[str, object]]:
                    limit = min(arguments.get("limit", 25), self._settings.max_result_items)
                    return [item.as_dict() for item in await self._service.list_items(limit)]

                async def _put_item(self, arguments: dict[str, Any]) -> dict[str, object]:
                    return (await self._service.put_item(arguments["item_id"], arguments["name"], arguments["expected_version"])).as_dict()

                @staticmethod
                def _failure(code: str, message: str, request_id: str, started: float) -> dict[str, Any]:
                    return {"success": False, "error": {"code": code, "message": message, "retryable": False}, "_meta": {"request_id": request_id, "duration_ms": int((time.monotonic() - started) * 1000)}}
            '''
        ),
        f"src/{package}/http.py": render(
            '''
            """ASGI boundary that bounds and buffers request bodies before MCP parsing."""

            from typing import Any

            class RequestBodyLimitMiddleware:
                def __init__(self, app: Any, max_bytes: int, max_events: int = 1_024) -> None:
                    if type(max_bytes) is not int or max_bytes <= 0:
                        raise ValueError("max_bytes must be a positive integer")
                    if type(max_events) is not int or not 1 <= max_events <= 10_000:
                        raise ValueError("max_events must be an integer between 1 and 10000")
                    self._app, self._max_bytes, self._max_events = app, max_bytes, max_events

                async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
                    if scope.get("type") != "http":
                        await self._app(scope, receive, send)
                        return
                    lengths: list[int] = []
                    for key, value in scope.get("headers", []):
                        if key.lower() != b"content-length":
                            continue
                        try:
                            parsed = int(value)
                        except (TypeError, ValueError):
                            await self._reject(send, 400, b"invalid content-length")
                            return
                        if parsed < 0:
                            await self._reject(send, 400, b"invalid content-length")
                            return
                        lengths.append(parsed)
                    if lengths and any(length != lengths[0] for length in lengths):
                        await self._reject(send, 400, b"conflicting content-length")
                        return
                    if lengths and lengths[0] > self._max_bytes:
                        await self._reject(send, 413, b"request body too large")
                        return

                    body = bytearray()
                    events = 0
                    while True:
                        events += 1
                        if events > self._max_events:
                            await self._reject(send, 413, b"too many request body chunks")
                            return
                        message = await receive()
                        message_type = message.get("type")
                        if message_type == "http.disconnect":
                            return
                        if message_type != "http.request":
                            await self._reject(send, 400, b"invalid request body event")
                            return
                        chunk = message.get("body", b"")
                        if not isinstance(chunk, bytes):
                            await self._reject(send, 400, b"invalid request body")
                            return
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            await self._reject(send, 413, b"request body too large")
                            return
                        if message.get("more_body") is not True:
                            break
                    if lengths and len(body) != lengths[0]:
                        await self._reject(send, 400, b"content-length mismatch")
                        return

                    replayed = False
                    async def replay_receive() -> dict[str, Any]:
                        nonlocal replayed
                        if not replayed:
                            replayed = True
                            return {"type": "http.request", "body": bytes(body), "more_body": False}
                        return await receive()
                    await self._app(scope, replay_receive, send)

                @staticmethod
                async def _reject(send: Any, status: int, body: bytes) -> None:
                    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
                    await send({"type": "http.response.body", "body": body})
            '''
        ),
        f"src/{package}/server.py": render(
            '''
            """Official MCP Python SDK composition root and transport entry point."""

            import json
            from collections.abc import AsyncIterator
            from contextlib import asynccontextmanager
            from dataclasses import dataclass
            from typing import Any

            import uvicorn
            from mcp.server.mcpserver import Context, MCPServer
            from mcp.server.mcpserver.exceptions import ToolError

            from __PACKAGE__.config import Settings
            from __PACKAGE__.domain import InventoryService
            from __PACKAGE__.http import RequestBodyLimitMiddleware
            from __PACKAGE__.kernel import ApprovalRegistry, CallerContext, InvocationKernel
            from __PACKAGE__.manifests import validate_manifests

            REGISTERED_TOOLS = {"describe_capabilities", "get_health", "list_items", "put_item"}

            @dataclass(frozen=True, slots=True)
            class AppContext:
                settings: Settings
                kernel: InvocationKernel

            def _require_success(result: dict[str, Any]) -> dict[str, Any]:
                if result.get("success") is True:
                    return result
                error = result.get("error") or {}
                raise ToolError(f"{error.get('code', 'ERROR')}: {error.get('message', 'operation failed')}")

            def build_server(settings: Settings | None = None, approvals: ApprovalRegistry | None = None) -> MCPServer[AppContext]:
                settings = (settings or Settings.from_env()).validate()
                approvals = approvals or ApprovalRegistry()
                validate_manifests(REGISTERED_TOOLS)

                kernel = InvocationKernel(settings, InventoryService(), approvals)

                @asynccontextmanager
                async def lifespan(_server: MCPServer[AppContext]) -> AsyncIterator[AppContext]:
                    yield AppContext(settings, kernel)

                mcp = MCPServer(
                    "__SERVER_NAME__",
                    instructions=(
                        "Use list_items before put_item. Preserve item_id and current version. "
                        "Writes are disabled by default and require a trusted-host one-time approval."
                    ),
                    version="0.1.0",
                    lifespan=lifespan,
                )

                @mcp.tool()
                async def describe_capabilities(ctx: Context[AppContext]) -> dict[str, Any]:
                    return _require_success(await ctx.request_context.lifespan_context.kernel.invoke("describe_capabilities", {}))

                @mcp.tool()
                async def get_health(ctx: Context[AppContext]) -> dict[str, Any]:
                    return _require_success(await ctx.request_context.lifespan_context.kernel.invoke("get_health", {}))

                @mcp.tool()
                async def list_items(ctx: Context[AppContext], limit: int = 25) -> dict[str, Any]:
                    return _require_success(await ctx.request_context.lifespan_context.kernel.invoke("list_items", {"limit": limit}))

                @mcp.tool()
                async def put_item(item_id: str, name: str, expected_version: int, ctx: Context[AppContext], approval_token: str | None = None) -> dict[str, Any]:
                    return _require_success(await ctx.request_context.lifespan_context.kernel.invoke(
                        "put_item", {"item_id": item_id, "name": name, "expected_version": expected_version},
                        CallerContext(approval_token=approval_token),
                    ))

                @mcp.resource("capabilities://catalog", mime_type="application/json")
                async def capability_catalog() -> str:
                    return json.dumps(kernel.catalog(), sort_keys=True)

                @mcp.resource("health://ready", mime_type="application/json")
                async def readiness() -> str:
                    return json.dumps({"ready": True, "transport": settings.transport, "active_capabilities": len(kernel.active_names)}, sort_keys=True)

                @mcp.prompt()
                def inventory_workflow() -> str:
                    return "List items first. Reuse stable item_id/current version. Never retry a write."

                return mcp

            def build_http_app(server: MCPServer[AppContext], settings: Settings) -> RequestBodyLimitMiddleware:
                if settings.transport != "streamable-http":
                    raise ValueError("build_http_app requires streamable-http settings")
                settings.validate()
                return RequestBodyLimitMiddleware(
                    server.streamable_http_app(
                        host=settings.host,
                        json_response=True,
                        stateless_http=True,
                        max_request_body_size=settings.max_request_body_bytes,
                    ),
                    settings.max_request_body_bytes,
                )

            def main() -> None:
                settings = Settings.from_env()
                server = build_server(settings)
                if settings.transport == "stdio":
                    server.run()
                else:
                    uvicorn.run(build_http_app(server, settings), host=settings.host, port=settings.port)

            if __name__ == "__main__":
                main()
            '''
        ),
        "tests/conftest.py": _clean(
            """
            import pytest

            @pytest.fixture
            def anyio_backend():
                return "asyncio"
            """
        ),
        "tests/test_config.py": render(
            """
            import pytest
            from __PACKAGE__.config import Settings
            from __PACKAGE__.server import build_http_app, build_server

            def test_http_transport_is_literal_loopback_only() -> None:
                Settings(transport="streamable-http", host="127.0.0.1").validate()
                Settings(transport="streamable-http", host="::1").validate()
                for host in ("0.0.0.0", "::", "192.168.1.10", "localhost"):
                    with pytest.raises(ValueError):
                        Settings(transport="streamable-http", host=host).validate()

            def test_direct_settings_are_type_checked() -> None:
                with pytest.raises(ValueError):
                    Settings(write_enabled="false").validate()  # type: ignore[arg-type]

            def test_http_builder_requires_http_settings() -> None:
                settings = Settings()
                with pytest.raises(ValueError):
                    build_http_app(build_server(settings), settings)
            """
        ),
        "tests/test_kernel.py": render(
            """
            import pytest
            from __PACKAGE__.config import Settings
            from __PACKAGE__.domain import InventoryService
            from __PACKAGE__.kernel import ApprovalRegistry, CallerContext, InvocationKernel

            PRINCIPAL = "local-stdio-user"

            @pytest.mark.anyio
            async def test_write_is_fail_closed_approved_once_and_versioned() -> None:
                service = InventoryService()
                approvals = ApprovalRegistry()
                disabled = InvocationKernel(Settings(write_enabled=False), service, approvals)
                denied = await disabled.invoke("put_item", {"item_id": "a", "name": "A", "expected_version": 0}, CallerContext(approval_token=approvals.issue("put_item", PRINCIPAL, "inventory", "a")))
                assert denied["error"]["code"] == "AUTHORIZATION_FAILED"
                enabled = InvocationKernel(Settings(write_enabled=True), service, approvals)
                no_approval = await enabled.invoke("put_item", {"item_id": "a", "name": "A", "expected_version": 0})
                assert no_approval["error"]["code"] == "AUTHORIZATION_FAILED"
                token = approvals.issue("put_item", PRINCIPAL, "inventory", "a")
                created = await enabled.invoke("put_item", {"item_id": "a", "name": "A", "expected_version": 0}, CallerContext(approval_token=token))
                assert created["success"] is True and created["data"]["version"] == 1
                replay = await enabled.invoke("put_item", {"item_id": "a", "name": "B", "expected_version": 1}, CallerContext(approval_token=token))
                assert replay["error"]["code"] == "AUTHORIZATION_FAILED"
                missing = await enabled.invoke("put_item", {"item_id": "a", "name": "B"}, CallerContext(approval_token=approvals.issue("put_item", PRINCIPAL, "inventory", "a")))
                assert missing["error"]["code"] == "VALIDATION_FAILED"

            def test_approval_registry_is_bounded() -> None:
                approvals = ApprovalRegistry(max_records=1)
                approvals.issue("put_item", PRINCIPAL, "inventory", "a")
                with pytest.raises(RuntimeError):
                    approvals.issue("put_item", PRINCIPAL, "inventory", "b")
            """
        ),
        "tests/test_manifests.py": render(
            """
            from __PACKAGE__.manifests import MANIFESTS, validate_manifests
            from __PACKAGE__.server import REGISTERED_TOOLS

            def test_manifest_coverage_and_conservative_write_defaults() -> None:
                validate_manifests(REGISTERED_TOOLS)
                assert set(MANIFESTS) == REGISTERED_TOOLS
                write = MANIFESTS["put_item"]
                assert write.idempotent is False
                assert write.retryable is False
                assert write.concurrent_safe is False
                assert "mandatory expected_version" in write.target_binding
            """
        ),
        "tests/test_http_limit.py": render(
            """
            import pytest
            from __PACKAGE__.http import RequestBodyLimitMiddleware

            async def _run(middleware, messages):
                sent = []
                iterator = iter(messages)
                async def receive():
                    return next(iterator)
                async def send(message):
                    sent.append(message)
                await middleware({"type": "http", "headers": []}, receive, send)
                return sent

            @pytest.mark.anyio
            async def test_oversized_chunked_body_is_rejected_before_application() -> None:
                called = False
                async def app(scope, receive, send):
                    nonlocal called
                    called = True
                middleware = RequestBodyLimitMiddleware(app, 3)
                sent = await _run(middleware, [
                    {"type": "http.request", "body": b"ab", "more_body": True},
                    {"type": "http.request", "body": b"cd", "more_body": False},
                ])
                assert not called and sent[0]["status"] == 413

            @pytest.mark.anyio
            async def test_replay_preserves_live_disconnect_stream() -> None:
                observed = []
                async def app(scope, receive, send):
                    observed.append(await receive())
                    observed.append(await receive())
                middleware = RequestBodyLimitMiddleware(app, 16)
                await _run(middleware, [
                    {"type": "http.request", "body": b"ok", "more_body": False},
                    {"type": "http.disconnect"},
                ])
                assert observed[0]["type"] == "http.request"
                assert observed[0]["body"] == b"ok"
                assert observed[1]["type"] == "http.disconnect"
            """
        ),
        "tests/test_mcp_smoke.py": render(
            """
            import pytest
            from mcp.client import Client
            from __PACKAGE__.config import Settings
            from __PACKAGE__.server import build_server

            @pytest.mark.anyio
            async def test_real_mcp_client_lists_and_calls_tool() -> None:
                server = build_server(Settings())
                async with Client(server, raise_exceptions=True) as client:
                    listed = await client.list_tools()
                    names = {tool.name for tool in listed.tools}
                    assert {"describe_capabilities", "get_health", "list_items", "put_item"}.issubset(names)
                    put_schema = next(tool.input_schema for tool in listed.tools if tool.name == "put_item")
                    assert "expected_version" in put_schema.get("required", [])
                    assert "confirmed" not in put_schema.get("properties", {})
                    result = await client.call_tool("list_items", {"limit": 10})
                    assert result.is_error is not True
                    assert result.structured_content is not None
                    structured = result.structured_content.get("result", result.structured_content)
                    assert structured["success"] is True
            """
        ),
    }


def _raise_rename_error(error_number: int, destination: Path) -> None:
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error_number, "generation target already exists", destination)
    raise OSError(error_number, os.strerror(error_number), destination)


def _runtime_platform() -> str:
    """Return the runtime platform without static narrowing by type checkers."""
    return sys.platform


def _runtime_os_name() -> str:
    """Return the runtime OS family without static narrowing by type checkers."""
    return os.name


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish one directory without replacing any destination object."""
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    platform_name = _runtime_platform()
    if platform_name.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise RuntimeError("atomic no-replace rename requires renameat2 on this Linux runtime")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        if renameat2(_AT_FDCWD, source_bytes, _AT_FDCWD, destination_bytes, _RENAME_NOREPLACE) != 0:
            _raise_rename_error(ctypes.get_errno(), destination)
        return
    if platform_name == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renamex_np = getattr(libc, "renamex_np", None)
        if renamex_np is None:
            raise RuntimeError("atomic no-replace rename requires renamex_np on this macOS runtime")
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        if renamex_np(source_bytes, destination_bytes, _RENAME_EXCL) != 0:
            _raise_rename_error(ctypes.get_errno(), destination)
        return
    if _runtime_os_name() == "nt":
        os.rename(source, destination)
        return
    raise RuntimeError("this platform has no configured atomic no-replace directory rename")


def generate_project(target: Path, package: str, server_name: str) -> list[Path]:
    """Generate a project atomically and never follow or replace the target leaf."""
    expanded = target.expanduser()
    target = expanded.parent.resolve(strict=False) / expanded.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(target):
        raise FileExistsError(errno.EEXIST, "generation target already exists", target)
    files = project_files(package, server_name)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    published = False
    try:
        for relative, content in sorted(files.items()):
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")
        _rename_noreplace(staging, target)
        published = True
        return [Path(relative) for relative in sorted(files)]
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="new project directory; must not exist")
    parser.add_argument("--package", required=True, help="Python package and console-script name")
    parser.add_argument("--name", required=True, dest="server_name", help="MCP server display name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    created = generate_project(args.target, args.package, args.server_name)
    print(f"Generated {len(created)} files in {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
