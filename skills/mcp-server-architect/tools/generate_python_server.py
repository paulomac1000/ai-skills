#!/usr/bin/env python3
"""Generate a runnable, production-shaped Python MCP server baseline."""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import textwrap
from pathlib import Path

PACKAGE_RE = re.compile(r"[a-z][a-z0-9_]{1,62}$")
SERVER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{1,78}$")


def _clean(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n").rstrip() + "\n"


def _render(text: str, *, package: str, server_name: str) -> str:
    return _clean(text).replace("__PACKAGE__", package).replace("__SERVER_NAME__", server_name)


def project_files(package: str, server_name: str) -> dict[str, str]:
    """Return the complete generated project as relative UTF-8 text files."""
    if not PACKAGE_RE.fullmatch(package):
        raise ValueError("package must match [a-z][a-z0-9_]{1,62}")
    if not SERVER_RE.fullmatch(server_name):
        raise ValueError("server name must be 2-79 safe display characters")

    files: dict[str, str] = {
        "pyproject.toml": _render(
            '''
            [build-system]
            requires = ["setuptools>=75", "wheel"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "__PACKAGE__"
            version = "0.1.0"
            description = "Production-shaped MCP server generated from the MCP server architect standard"
            requires-python = ">=3.12"
            dependencies = ["mcp>=1.27.2,<2"]

            [project.optional-dependencies]
            dev = ["pytest==9.0.2"]

            [project.scripts]
            __PACKAGE__ = "__PACKAGE__.server:main"

            [tool.setuptools.packages.find]
            where = ["src"]

            [tool.pytest.ini_options]
            testpaths = ["tests"]
            addopts = "-q"
            ''', package=package, server_name=server_name),
        "README.md": _render(
            '''
            # __SERVER_NAME__

            Generated production baseline for an MCP server. It deliberately separates domain code,
            capability manifests, the invocation kernel, SDK registration, and transport startup.

            ## Run

            ```bash
            python -m venv .venv
            . .venv/bin/activate
            pip install -e ".[dev]"
            __PACKAGE__
            ```

            Stdio is the default. For Streamable HTTP:

            ```bash
            MCP_TRANSPORT=streamable-http MCP_HOST=127.0.0.1 MCP_PORT=8000 __PACKAGE__
            ```

            HTTP intentionally binds to loopback by default. Add real authentication and
            resource-scoped authorization before exposing a remote transport.

            ## Before production

            Replace the in-memory domain adapter, review every manifest, connect authorization to a
            real principal, add upstream contract tests, and smoke-test the built wheel or container.
            A generated scaffold is a verified starting point, not evidence for domain-specific safety.
            ''', package=package, server_name=server_name),
        ".env.example": _render(
            '''
            MCP_TRANSPORT=stdio
            MCP_HOST=127.0.0.1
            MCP_PORT=8000
            MCP_WRITE_ENABLED=false
            MCP_DEFAULT_DEADLINE_MS=10000
            MCP_MAX_RESULT_ITEMS=100
            ''', package=package, server_name=server_name),
        ".gitignore": _clean('''
            .env
            .venv/
            __pycache__/
            .pytest_cache/
            *.pyc
            build/
            dist/
            *.egg-info/
        '''),
        "Dockerfile": _render(
            '''
            FROM python:3.12-slim
            WORKDIR /app
            RUN useradd --create-home --uid 10001 appuser
            COPY pyproject.toml README.md ./
            COPY src ./src
            RUN pip install --no-cache-dir .
            USER appuser
            ENV MCP_TRANSPORT=stdio
            ENTRYPOINT ["__PACKAGE__"]
            ''', package=package, server_name=server_name),
        "SECURITY.md": _clean(
            '''
            # Security model

            The generated project is local-first. Stdio and loopback-only Streamable HTTP are the
            supported baseline. Write operations are disabled unless the operator explicitly enables
            them, and the sample mutation also requires exact confirmation and optimistic concurrency.

            Before remote or multi-user deployment, add authenticated principal extraction,
            resource-scoped authorization, TLS or a reviewed reverse proxy, restrictive Origin and Host
            policy, quotas, audit retention, and deployment-specific secret storage.
            '''
        ),
        ".github/workflows/ci.yml": _clean(
            '''
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
                  - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1
                    with:
                      persist-credentials: false
                  - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
                    with:
                      python-version: "3.12"
                      cache: pip
                      cache-dependency-path: pyproject.toml
                  - run: python -m pip install -e ".[dev]"
                  - run: python -m compileall -q src tests
                  - run: python -m pytest
            '''
        ),
        f"src/{package}/__init__.py": _clean('''
            """Generated MCP server package."""

            __all__ = ["__version__"]
            __version__ = "0.1.0"
        '''),
        f"src/{package}/__main__.py": _render(
            '''
            from __PACKAGE__.server import main

            if __name__ == "__main__":
                main()
            ''', package=package, server_name=server_name),
        f"src/{package}/config.py": _render(
            '''
            """Typed, immutable process configuration loaded before dependency construction."""

            from __future__ import annotations

            import os
            from dataclasses import dataclass
            from typing import Literal

            Transport = Literal["stdio", "streamable-http"]


            def _boolean(name: str, default: bool) -> bool:
                raw = os.getenv(name)
                if raw is None:
                    return default
                normalized = raw.strip().casefold()
                if normalized in {"1", "true", "yes", "on"}:
                    return True
                if normalized in {"0", "false", "no", "off"}:
                    return False
                raise ValueError(f"{name} must be a boolean")


            def _integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
                raw = os.getenv(name)
                value = default if raw is None else int(raw)
                if not minimum <= value <= maximum:
                    raise ValueError(f"{name} must be between {minimum} and {maximum}")
                return value


            @dataclass(frozen=True, slots=True)
            class Settings:
                transport: Transport = "stdio"
                host: str = "127.0.0.1"
                port: int = 8000
                write_enabled: bool = False
                default_deadline_ms: int = 10_000
                max_result_items: int = 100

                @classmethod
                def from_env(cls) -> "Settings":
                    transport = os.getenv("MCP_TRANSPORT", "stdio").strip().casefold()
                    if transport not in {"stdio", "streamable-http"}:
                        raise ValueError("MCP_TRANSPORT must be stdio or streamable-http")
                    host = os.getenv("MCP_HOST", "127.0.0.1").strip()
                    if not host:
                        raise ValueError("MCP_HOST cannot be empty")
                    if host == "0.0.0.0":
                        raise ValueError(
                            "Generated baseline refuses public binding; add authentication, authorization, "
                            "TLS/proxy policy, Origin validation, and an explicit deployment review first"
                        )
                    return cls(
                        transport=transport,  # type: ignore[arg-type]
                        host=host,
                        port=_integer("MCP_PORT", 8000, minimum=1, maximum=65_535),
                        write_enabled=_boolean("MCP_WRITE_ENABLED", False),
                        default_deadline_ms=_integer(
                            "MCP_DEFAULT_DEADLINE_MS", 10_000, minimum=100, maximum=120_000
                        ),
                        max_result_items=_integer(
                            "MCP_MAX_RESULT_ITEMS", 100, minimum=1, maximum=1_000
                        ),
                    )
            ''', package=package, server_name=server_name),
        f"src/{package}/manifests.py": _render(
            '''
            """Application-owned capability manifests; missing metadata is a startup error."""

            from __future__ import annotations

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


            MANIFESTS: dict[str, CapabilityManifest] = {
                "describe_capabilities": CapabilityManifest(
                    name="describe_capabilities",
                    version="1.0.0",
                    side_effects="read",
                    confidentiality="public",
                    operational_impact="none",
                    cost="cheap",
                    reversible=True,
                    idempotent=True,
                    idempotency_mechanism="pure process-local catalog",
                    retryable=False,
                    retry_conditions=(),
                    concurrent_safe=True,
                    concurrency_scope="none",
                    timeout_ms=1_000,
                    requires_confirmation=False,
                    target_binding="process capability catalog",
                ),
                "get_health": CapabilityManifest(
                    name="get_health",
                    version="1.0.0",
                    side_effects="read",
                    confidentiality="internal",
                    operational_impact="none",
                    cost="cheap",
                    reversible=True,
                    idempotent=True,
                    idempotency_mechanism="process-local readiness snapshot",
                    retryable=False,
                    retry_conditions=(),
                    concurrent_safe=True,
                    concurrency_scope="none",
                    timeout_ms=1_000,
                    requires_confirmation=False,
                    target_binding="process runtime",
                ),
                "list_items": CapabilityManifest(
                    name="list_items",
                    version="1.0.0",
                    side_effects="read",
                    confidentiality="internal",
                    operational_impact="none",
                    cost="cheap",
                    reversible=True,
                    idempotent=True,
                    idempotency_mechanism="natural read",
                    retryable=True,
                    retry_conditions=("transient_unavailable_before_response",),
                    concurrent_safe=True,
                    concurrency_scope="inventory",
                    timeout_ms=5_000,
                    requires_confirmation=False,
                    target_binding="process inventory",
                ),
                "put_item": CapabilityManifest(
                    name="put_item",
                    version="1.0.0",
                    side_effects="write",
                    confidentiality="internal",
                    operational_impact="persistent",
                    cost="cheap",
                    reversible=True,
                    idempotent=False,
                    idempotency_mechanism=None,
                    retryable=False,
                    retry_conditions=(),
                    concurrent_safe=False,
                    concurrency_scope="inventory item",
                    timeout_ms=5_000,
                    requires_confirmation=True,
                    target_binding="stable item_id plus expected_version",
                ),
            }


            def validate_manifests(registered_names: set[str]) -> None:
                manifest_names = set(MANIFESTS)
                missing = registered_names - manifest_names
                orphaned = manifest_names - registered_names
                if missing or orphaned:
                    raise RuntimeError(
                        f"manifest coverage mismatch: missing={sorted(missing)}, orphaned={sorted(orphaned)}"
                    )
                for manifest in MANIFESTS.values():
                    if manifest.timeout_ms <= 0:
                        raise RuntimeError(f"invalid timeout for {manifest.name}")
                    if manifest.retryable and not manifest.idempotent:
                        raise RuntimeError(f"retryable capability lacks idempotency proof: {manifest.name}")
                    if manifest.side_effects != "read" and manifest.retryable:
                        raise RuntimeError(f"generated writes must default to non-retryable: {manifest.name}")
            ''', package=package, server_name=server_name),
        f"src/{package}/domain.py": _render(
            '''
            """Transport-independent domain service and deterministic in-memory adapter."""

            from __future__ import annotations

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
                    self._items: dict[str, Item] = {"example": Item("example", "Example item", 1)}
                    self._lock = asyncio.Lock()

                async def list_items(self, *, limit: int) -> list[Item]:
                    if not 1 <= limit <= 1_000:
                        raise ValueError("limit must be between 1 and 1000")
                    return sorted(self._items.values(), key=lambda item: item.item_id)[:limit]

                async def put_item(
                    self, *, item_id: str, name: str, expected_version: int | None
                ) -> Item:
                    if not item_id or len(item_id) > 64:
                        raise ValueError("item_id must contain 1-64 characters")
                    if not name.strip() or len(name) > 200:
                        raise ValueError("name must contain 1-200 characters")
                    async with self._lock:
                        current = self._items.get(item_id)
                        current_version = current.version if current else 0
                        if expected_version is not None and expected_version != current_version:
                            raise ConflictError(
                                f"stale expected_version={expected_version}; current_version={current_version}"
                            )
                        updated = Item(item_id=item_id, name=name.strip(), version=current_version + 1)
                        self._items[item_id] = updated
                        return updated
            ''', package=package, server_name=server_name),
        f"src/{package}/kernel.py": _render(
            '''
            """Single invocation kernel shared by MCP and any future adapters."""

            from __future__ import annotations

            import asyncio
            import contextvars
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
                confirmed: bool = False


            class InvocationKernel:
                def __init__(self, settings: Settings, service: InventoryService) -> None:
                    self._settings = settings
                    self._service = service
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

                async def invoke(
                    self,
                    name: str,
                    arguments: dict[str, Any],
                    caller: CallerContext | None = None,
                ) -> dict[str, Any]:
                    caller = caller or CallerContext()
                    request_id = uuid.uuid4().hex
                    token = _request_id.set(request_id)
                    started = time.monotonic()
                    try:
                        manifest = self._resolve_manifest(name)
                        self._authorize(manifest, caller)
                        timeout_seconds = min(
                            manifest.timeout_ms, self._settings.default_deadline_ms
                        ) / 1000
                        lock = self._lock_for(manifest, arguments)
                        async with asyncio.timeout(timeout_seconds):
                            if lock is None:
                                data = await self._handlers[name](arguments)
                            else:
                                async with lock:
                                    data = await self._handlers[name](arguments)
                        return {
                            "success": True,
                            "data": data,
                            "_meta": {
                                "request_id": request_id,
                                "target_id": caller.target_id,
                                "duration_ms": int((time.monotonic() - started) * 1000),
                            },
                        }
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
                        return self._failure(
                            "INTERNAL_ERROR", "internal operation failure", request_id, started
                        )
                    finally:
                        _request_id.reset(token)

                def catalog(self) -> list[dict[str, object]]:
                    return [MANIFESTS[name].as_dict() for name in sorted(self.active_names)]

                def _resolve_manifest(self, name: str) -> CapabilityManifest:
                    manifest = MANIFESTS.get(name)
                    if manifest is None or not manifest.active or name not in self._handlers:
                        raise ValueError(f"unknown or inactive capability: {name}")
                    return manifest

                def _authorize(self, manifest: CapabilityManifest, caller: CallerContext) -> None:
                    if caller.target_id != "inventory":
                        raise PermissionError("target is not authorized")
                    if manifest.side_effects != "read":
                        if not self._settings.write_enabled:
                            raise PermissionError("write operations are disabled by operator policy")
                        if manifest.requires_confirmation and not caller.confirmed:
                            raise PermissionError("exact operation confirmation is required")

                def _lock_for(
                    self, manifest: CapabilityManifest, arguments: dict[str, Any]
                ) -> asyncio.Lock | None:
                    if manifest.concurrent_safe:
                        return None
                    stable_key = str(arguments.get("item_id") or manifest.concurrency_scope)
                    return self._locks.setdefault(stable_key, asyncio.Lock())

                async def _describe_capabilities(
                    self, _arguments: dict[str, Any]
                ) -> list[dict[str, object]]:
                    return self.catalog()

                async def _get_health(self, _arguments: dict[str, Any]) -> dict[str, object]:
                    return {
                        "ready": True,
                        "active_capabilities": len(self.active_names),
                        "write_enabled": self._settings.write_enabled,
                    }

                async def _list_items(self, arguments: dict[str, Any]) -> list[dict[str, object]]:
                    limit = int(arguments.get("limit", 25))
                    limit = min(limit, self._settings.max_result_items)
                    items = await self._service.list_items(limit=limit)
                    return [item.as_dict() for item in items]

                async def _put_item(self, arguments: dict[str, Any]) -> dict[str, object]:
                    item = await self._service.put_item(
                        item_id=str(arguments.get("item_id", "")),
                        name=str(arguments.get("name", "")),
                        expected_version=arguments.get("expected_version"),
                    )
                    return item.as_dict()

                @staticmethod
                def _failure(
                    code: str, message: str, request_id: str, started: float
                ) -> dict[str, Any]:
                    return {
                        "success": False,
                        "error": {"code": code, "message": message, "retryable": False},
                        "_meta": {
                            "request_id": request_id,
                            "duration_ms": int((time.monotonic() - started) * 1000),
                        },
                    }
            ''', package=package, server_name=server_name),
        f"src/{package}/server.py": _render(
            '''
            """Official MCP Python SDK composition root and transport entry point."""

            from __future__ import annotations

            import json
            from collections.abc import AsyncIterator
            from contextlib import asynccontextmanager
            from dataclasses import dataclass
            from typing import Any

            from mcp.server.fastmcp import Context, FastMCP
            from mcp.server.fastmcp.exceptions import ToolError
            from mcp.server.session import ServerSession

            from __PACKAGE__.config import Settings
            from __PACKAGE__.domain import InventoryService
            from __PACKAGE__.kernel import CallerContext, InvocationKernel
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


            def build_server(settings: Settings | None = None) -> FastMCP:
                settings = settings or Settings.from_env()
                validate_manifests(REGISTERED_TOOLS)

                @asynccontextmanager
                async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
                    service = InventoryService()
                    kernel = InvocationKernel(settings=settings, service=service)
                    yield AppContext(settings=settings, kernel=kernel)

                mcp = FastMCP(
                    "__SERVER_NAME__",
                    instructions=(
                        "Use list_items before put_item. Writes are disabled by default and require "
                        "operator enablement plus exact confirmation. Preserve returned item_id and version."
                    ),
                    lifespan=lifespan,
                    host=settings.host,
                    port=settings.port,
                    stateless_http=True,
                    json_response=True,
                    max_request_body_size=1_048_576,
                )

                @mcp.tool()
                async def describe_capabilities(
                    ctx: Context[ServerSession, AppContext],
                ) -> dict[str, Any]:
                    """Describe active capabilities and their governed manifests without upstream I/O."""
                    result = await ctx.request_context.lifespan_context.kernel.invoke(
                        "describe_capabilities", {}
                    )
                    return _require_success(result)

                @mcp.tool()
                async def get_health(
                    ctx: Context[ServerSession, AppContext],
                ) -> dict[str, Any]:
                    """Return a bounded readiness snapshot for mandatory runtime dependencies."""
                    result = await ctx.request_context.lifespan_context.kernel.invoke("get_health", {})
                    return _require_success(result)

                @mcp.tool()
                async def list_items(
                    ctx: Context[ServerSession, AppContext], limit: int = 25
                ) -> dict[str, Any]:
                    """List bounded inventory summaries in stable item_id order."""
                    result = await ctx.request_context.lifespan_context.kernel.invoke(
                        "list_items", {"limit": limit}
                    )
                    return _require_success(result)

                @mcp.tool()
                async def put_item(
                    item_id: str,
                    name: str,
                    ctx: Context[ServerSession, AppContext],
                    expected_version: int | None = None,
                    confirmed: bool = False,
                ) -> dict[str, Any]:
                    """Create or update one item using optimistic concurrency."""
                    app = ctx.request_context.lifespan_context
                    result = await app.kernel.invoke(
                        "put_item",
                        {
                            "item_id": item_id,
                            "name": name,
                            "expected_version": expected_version,
                        },
                        CallerContext(confirmed=confirmed),
                    )
                    return _require_success(result)

                @mcp.resource("capabilities://catalog", mime_type="application/json")
                async def capability_catalog(
                    ctx: Context[ServerSession, AppContext],
                ) -> str:
                    """Return the active, governed capability catalog without upstream I/O."""
                    return json.dumps(
                        ctx.request_context.lifespan_context.kernel.catalog(), sort_keys=True
                    )

                @mcp.resource("health://ready", mime_type="application/json")
                async def readiness(ctx: Context[ServerSession, AppContext]) -> str:
                    """Report readiness for the generated in-memory mandatory dependency."""
                    app = ctx.request_context.lifespan_context
                    return json.dumps(
                        {
                            "ready": True,
                            "transport": app.settings.transport,
                            "active_capabilities": len(app.kernel.active_names),
                        },
                        sort_keys=True,
                    )

                @mcp.prompt()
                def inventory_workflow() -> str:
                    """Guide an agent through the version-aware inventory workflow."""
                    return (
                        "List items first. For updates, reuse the stable item_id and current version. "
                        "Do not retry a failed write automatically."
                    )

                return mcp


            app = build_server(Settings())


            def main() -> None:
                settings = Settings.from_env()
                server = build_server(settings)
                if settings.transport == "stdio":
                    server.run()
                else:
                    server.run(transport="streamable-http")


            if __name__ == "__main__":
                main()
            ''', package=package, server_name=server_name),
        "tests/conftest.py": _clean(
            '''
            import pytest


            @pytest.fixture
            def anyio_backend():
                return "asyncio"
            '''
        ),
        "tests/test_kernel.py": _render(
            '''
            import pytest

            from __PACKAGE__.config import Settings
            from __PACKAGE__.domain import InventoryService
            from __PACKAGE__.kernel import CallerContext, InvocationKernel


            @pytest.mark.anyio
            async def test_write_is_fail_closed_and_versioned() -> None:
                service = InventoryService()
                disabled = InvocationKernel(Settings(write_enabled=False), service)
                denied = await disabled.invoke(
                    "put_item", {"item_id": "a", "name": "A", "expected_version": 0},
                    CallerContext(confirmed=True),
                )
                assert denied["success"] is False
                assert denied["error"]["code"] == "AUTHORIZATION_FAILED"

                enabled = InvocationKernel(Settings(write_enabled=True), service)
                created = await enabled.invoke(
                    "put_item", {"item_id": "a", "name": "A", "expected_version": 0},
                    CallerContext(confirmed=True),
                )
                assert created["success"] is True
                assert created["data"]["version"] == 1

                conflict = await enabled.invoke(
                    "put_item", {"item_id": "a", "name": "B", "expected_version": 0},
                    CallerContext(confirmed=True),
                )
                assert conflict["success"] is False
                assert conflict["error"]["code"] == "CONFLICT"
            ''', package=package, server_name=server_name),
        "tests/test_manifests.py": _render(
            '''
            from __PACKAGE__.manifests import MANIFESTS, validate_manifests
            from __PACKAGE__.server import REGISTERED_TOOLS


            def test_manifest_coverage_and_conservative_write_defaults() -> None:
                validate_manifests(REGISTERED_TOOLS)
                assert set(MANIFESTS) == REGISTERED_TOOLS
                write = MANIFESTS["put_item"]
                assert write.idempotent is False
                assert write.retryable is False
                assert write.concurrent_safe is False
            ''', package=package, server_name=server_name),
        "tests/test_mcp_smoke.py": _render(
            '''
            import pytest
            from mcp.shared.memory import create_connected_server_and_client_session

            from __PACKAGE__.config import Settings
            from __PACKAGE__.server import build_server


            @pytest.mark.anyio
            async def test_real_mcp_client_lists_and_calls_tool() -> None:
                server = build_server(Settings())
                async with create_connected_server_and_client_session(
                    server, raise_exceptions=True
                ) as session:
                    listed = await session.list_tools()
                    names = {tool.name for tool in listed.tools}
                    assert {"describe_capabilities", "get_health", "list_items", "put_item"}.issubset(names)
                    result = await session.call_tool("list_items", {"limit": 10})
                    assert result.isError is not True
                    assert result.structuredContent is not None
                    structured = result.structuredContent.get("result", result.structuredContent)
                    assert structured["success"] is True
            ''', package=package, server_name=server_name),
    }
    return files


def generate_project(target: Path, package: str, server_name: str) -> list[Path]:
    """Generate a complete project atomically; refuse to overwrite an existing path."""
    target = target.expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    created: list[Path] = []
    try:
        for relative, content in project_files(package, server_name).items():
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")
            created.append(Path(relative))
        staging.replace(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return sorted(created)


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
