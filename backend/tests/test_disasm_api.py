"""
TDD Tests for Disasm API endpoints.
"""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

# Add backend root to path
backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def client() -> TestClient:
    """Create test client for the FastAPI app."""
    from src.main import app
    # Clear disasm service before each test
    from src.services.disasm_service import disasm_service
    disasm_service.clear()
    with TestClient(app) as c:
        yield c
    disasm_service.clear()


@pytest.fixture
def arm32_elf_bytes() -> bytes:
    """Minimal ARM32 ELF binary."""
    from tests.conftest import make_minimal_arm32_elf
    return make_minimal_arm32_elf()


@pytest.fixture
def arm32_elf_with_symbols_bytes() -> bytes:
    """ARM32 ELF with function symbols."""
    from tests.conftest import make_minimal_arm32_elf
    return make_minimal_arm32_elf(
        entry=0x08000100,
        symbols=[
            ("main", 0x08000100, 12),
            ("helper_func", 0x08000200, 8),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 1: Upload
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpload:
    """Tests for /api/disasm/upload endpoint."""

    def test_upload_elf(self, client: TestClient, arm32_elf_bytes: bytes) -> None:
        """Upload an ELF file."""
        response = client.post(
            "/api/disasm/upload",
            files={"file": ("test.elf", BytesIO(arm32_elf_bytes), "application/octet-stream")},
            data={"arch": "auto", "base_addr": "0x0"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["meta"]["is_elf"] is True
        assert data["meta"]["arch"] == "arm"

    def test_upload_raw_binary(self, client: TestClient) -> None:
        """Upload a raw binary with explicit architecture."""
        raw = bytes([
            0x10, 0x40, 0x2d, 0xe9,  # push {r4, lr}
            0x00, 0x40, 0xa0, 0xe3,  # mov r4, #0
            0x10, 0x40, 0xbd, 0xe8,  # pop {r4, pc}
        ])
        response = client.post(
            "/api/disasm/upload",
            files={"file": ("raw.bin", BytesIO(raw), "application/octet-stream")},
            data={"arch": "arm", "base_addr": "0x08000000"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["is_elf"] is False
        assert data["meta"]["arch"] == "arm"
        assert data["meta"]["entry_point"] == 0x08000000

    def test_upload_invalid_arch(self, client: TestClient) -> None:
        """Upload with invalid architecture should fail."""
        raw = b"\x00\x01\x02\x03"
        response = client.post(
            "/api/disasm/upload",
            files={"file": ("raw.bin", BytesIO(raw), "application/octet-stream")},
            data={"arch": "invalid", "base_addr": "0x0"},
        )
        assert response.status_code == 422

    def test_upload_auto_non_elf(self, client: TestClient) -> None:
        """Upload non-ELF with arch=auto should fail."""
        raw = b"\x00\x01\x02\x03"
        response = client.post(
            "/api/disasm/upload",
            files={"file": ("raw.bin", BytesIO(raw), "application/octet-stream")},
            data={"arch": "auto", "base_addr": "0x0"},
        )
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 2: Status
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatus:
    """Tests for /api/disasm/status endpoint."""

    def test_status_no_file(self, client: TestClient) -> None:
        """Status when no file loaded."""
        response = client.get("/api/disasm/status")
        assert response.status_code == 200
        data = response.json()
        assert data["loaded"] is False
        assert data["meta"] is None

    def test_status_with_file(self, client: TestClient, arm32_elf_bytes: bytes) -> None:
        """Status after uploading a file."""
        # Upload first
        client.post(
            "/api/disasm/upload",
            files={"file": ("test.elf", BytesIO(arm32_elf_bytes), "application/octet-stream")},
            data={"arch": "auto", "base_addr": "0x0"},
        )
        # Check status
        response = client.get("/api/disasm/status")
        assert response.status_code == 200
        data = response.json()
        assert data["loaded"] is True
        assert data["meta"]["filename"] == "test.elf"


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 3: Disassembly
# ═══════════════════════════════════════════════════════════════════════════════

class TestDisassembly:
    """Tests for /api/disasm/disassembly endpoint."""

    def test_get_disassembly(self, client: TestClient, arm32_elf_bytes: bytes) -> None:
        """Get disassembly after upload."""
        client.post(
            "/api/disasm/upload",
            files={"file": ("test.elf", BytesIO(arm32_elf_bytes), "application/octet-stream")},
            data={"arch": "auto", "base_addr": "0x0"},
        )
        response = client.get("/api/disasm/disassembly")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert len(data["lines"]) >= 3

    def test_disassembly_pagination(self, client: TestClient, arm32_elf_bytes: bytes) -> None:
        """Test disassembly pagination."""
        client.post(
            "/api/disasm/upload",
            files={"file": ("test.elf", BytesIO(arm32_elf_bytes), "application/octet-stream")},
            data={"arch": "auto", "base_addr": "0x0"},
        )
        # Get first page
        r1 = client.get("/api/disasm/disassembly?offset=0&limit=2")
        # Get second page
        r2 = client.get("/api/disasm/disassembly?offset=2&limit=2")
        assert r1.status_code == 200
        assert r2.status_code == 200
        d1, d2 = r1.json(), r2.json()
        assert len(d1["lines"]) == 2
        assert d2["offset"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 4: Symbols
# ═══════════════════════════════════════════════════════════════════════════════

class TestSymbols:
    """Tests for /api/disasm/symbols endpoint."""

    def test_get_symbols(
        self, client: TestClient, arm32_elf_with_symbols_bytes: bytes
    ) -> None:
        """Get symbols after upload."""
        client.post(
            "/api/disasm/upload",
            files={"file": ("test_sym.elf", BytesIO(arm32_elf_with_symbols_bytes), "application/octet-stream")},
            data={"arch": "auto", "base_addr": "0x0"},
        )
        response = client.get("/api/disasm/symbols")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2
        names = {s["name"] for s in data["symbols"]}
        assert "main" in names

    def test_symbol_search(
        self, client: TestClient, arm32_elf_with_symbols_bytes: bytes
    ) -> None:
        """Search symbols by name."""
        client.post(
            "/api/disasm/upload",
            files={"file": ("test_sym.elf", BytesIO(arm32_elf_with_symbols_bytes), "application/octet-stream")},
            data={"arch": "auto", "base_addr": "0x0"},
        )
        response = client.get("/api/disasm/symbols?query=main")
        assert response.status_code == 200
        data = response.json()
        assert len(data["symbols"]) >= 1
        assert data["symbols"][0]["name"] == "main"


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 5: Resolve
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolve:
    """Tests for /api/disasm/resolve endpoint."""

    def test_resolve_address(
        self, client: TestClient, arm32_elf_with_symbols_bytes: bytes
    ) -> None:
        """Resolve address to function."""
        client.post(
            "/api/disasm/upload",
            files={"file": ("test_sym.elf", BytesIO(arm32_elf_with_symbols_bytes), "application/octet-stream")},
            data={"arch": "auto", "base_addr": "0x0"},
        )
        response = client.get("/api/disasm/resolve?address=0x08000104")
        assert response.status_code == 200
        data = response.json()
        assert data["address"] == 0x08000104
        assert data["function"] == "main"
        assert data["offset"] == 4

    def test_resolve_invalid_address(self, client: TestClient) -> None:
        """Resolve with invalid address should fail."""
        response = client.get("/api/disasm/resolve?address=invalid")
        assert response.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 6: Analyze
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyze:
    """Tests for /api/disasm/analyze endpoint."""

    def test_analyze_logs(
        self, client: TestClient, arm32_elf_with_symbols_bytes: bytes
    ) -> None:
        """Analyze crash logs."""
        client.post(
            "/api/disasm/upload",
            files={"file": ("test_sym.elf", BytesIO(arm32_elf_with_symbols_bytes), "application/octet-stream")},
            data={"arch": "auto", "base_addr": "0x0"},
        )
        response = client.post(
            "/api/disasm/analyze",
            json={
                "log_entries": [
                    "PC is at 0x08000104",
                    "LR is at 0x08000204",
                ],
                "device": "cortex-a7",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["anomalies"]) >= 1
        assert data["anomalies"][0]["function"] == "main"


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 7: Clear
# ═══════════════════════════════════════════════════════════════════════════════

class TestClear:
    """Tests for DELETE /api/disasm/clear endpoint."""

    def test_clear(self, client: TestClient, arm32_elf_bytes: bytes) -> None:
        """Clear loaded binary."""
        # Upload
        client.post(
            "/api/disasm/upload",
            files={"file": ("test.elf", BytesIO(arm32_elf_bytes), "application/octet-stream")},
            data={"arch": "auto", "base_addr": "0x0"},
        )
        # Verify loaded
        r1 = client.get("/api/disasm/status")
        assert r1.json()["loaded"] is True

        # Clear
        r2 = client.delete("/api/disasm/clear")
        assert r2.status_code == 200

        # Verify cleared
        r3 = client.get("/api/disasm/status")
        assert r3.json()["loaded"] is False
