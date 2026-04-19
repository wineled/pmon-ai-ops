"""
TDD Tests for DisasmService.
Tests are written BEFORE implementation to drive the design.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

# Add backend root to path for proper imports
backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

# Import the service - will fail until we implement it
# This is intentional TDD: tests define the interface


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 1: ELF Parsing
# ═══════════════════════════════════════════════════════════════════════════════

class TestELFParsing:
    """Tests for ELF header parsing and architecture detection."""
    
    def test_elf_magic_detection(self, arm32_elf: bytes) -> None:
        """Verify ELF magic number is correctly detected."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        meta = svc.load_binary(arm32_elf, "test.elf")
        
        assert meta.is_elf is True
        assert meta.arch == "arm"
        assert meta.bits == 32
    
    def test_elf_arm64_detection(self, arm64_elf: bytes) -> None:
        """Verify AArch64 ELF is correctly detected."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        meta = svc.load_binary(arm64_elf, "test64.elf")
        
        assert meta.is_elf is True
        assert meta.arch == "arm64"
        assert meta.bits == 64
    
    def test_elf_riscv_detection(self, riscv_elf: bytes) -> None:
        """Verify RISC-V ELF is correctly detected."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        meta = svc.load_binary(riscv_elf, "test.riscv.elf")
        
        assert meta.is_elf is True
        assert meta.arch == "riscv"
    
    def test_elf_entry_point(self, arm32_elf: bytes) -> None:
        """Verify entry point is extracted from ELF header."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        meta = svc.load_binary(arm32_elf, "test.elf")
        
        assert meta.entry_point == 0x08000100
    
    def test_non_elf_rejected(self) -> None:
        """Non-ELF binary should be rejected when arch='auto'."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        raw = b"\x00\x01\x02\x03"  # Not an ELF
        
        with pytest.raises(ValueError, match="Not an ELF file"):
            svc.load_binary(raw, "raw.bin", arch="auto")


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 2: Raw Binary Loading
# ═══════════════════════════════════════════════════════════════════════════════

class TestRawBinaryLoading:
    """Tests for loading raw binaries (no ELF header)."""
    
    def test_raw_binary_with_explicit_arch(self, raw_arm_binary: bytes) -> None:
        """Raw binary can be loaded with explicit architecture."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        meta = svc.load_binary(
            raw_arm_binary,
            "raw.bin",
            arch="arm",
            base_addr=0x08000000,
        )
        
        assert meta.is_elf is False
        assert meta.arch == "arm"
        assert meta.bits == 32
        assert meta.entry_point == 0x08000000
    
    def test_raw_binary_invalid_arch(self, raw_arm_binary: bytes) -> None:
        """Invalid architecture should raise error."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        
        with pytest.raises(ValueError, match="Unsupported architecture"):
            svc.load_binary(raw_arm_binary, "raw.bin", arch="invalid")


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 3: Capstone Disassembly
# ═══════════════════════════════════════════════════════════════════════════════

class TestCapstoneDisassembly:
    """Tests for Capstone-based disassembly."""
    
    def test_disassemble_arm_instructions(self, arm32_elf: bytes) -> None:
        """Verify ARM instructions are correctly disassembled."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm32_elf, "test.elf")
        
        result = svc.get_disassembly(offset=0, limit=10)
        
        assert result.total >= 3  # At least 3 instructions
        assert len(result.lines) >= 3
        
        # First instruction should be at entry point
        first = result.lines[0]
        assert first.address == 0x08000100
        assert first.mnemonic in ("push", "stmdb", "stmfd")  # ARM push variations
    
    def test_disassemble_arm64_instructions(self, arm64_elf: bytes) -> None:
        """Verify AArch64 instructions are correctly disassembled."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm64_elf, "test64.elf")
        
        result = svc.get_disassembly(offset=0, limit=10)
        
        assert result.total >= 4
        first = result.lines[0]
        assert first.address == 0x400000
        assert first.mnemonic == "stp"
    
    def test_disassembly_pagination(self, arm32_elf: bytes) -> None:
        """Verify disassembly pagination works correctly."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm32_elf, "test.elf")
        
        # Get first page
        page1 = svc.get_disassembly(offset=0, limit=2)
        # Get second page
        page2 = svc.get_disassembly(offset=2, limit=2)
        
        assert len(page1.lines) == 2
        assert page1.offset == 0
        assert page2.offset == 2
        
        # Pages should not overlap
        addrs1 = {l.address for l in page1.lines}
        addrs2 = {l.address for l in page2.lines}
        assert addrs1.isdisjoint(addrs2)
    
    def test_disassembly_no_binary_loaded(self) -> None:
        """get_disassembly should return empty when no binary loaded."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        result = svc.get_disassembly()
        
        assert result.total == 0
        assert result.lines == []


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 4: Symbol Table Parsing
# ═══════════════════════════════════════════════════════════════════════════════

class TestSymbolParsing:
    """Tests for ELF symbol table parsing."""
    
    def test_symbol_count(self, arm32_elf_with_symbols: bytes) -> None:
        """Verify symbols are parsed from ELF."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        meta = svc.load_binary(arm32_elf_with_symbols, "test_sym.elf")
        
        assert meta.symbol_count >= 2  # main + helper_func
    
    def test_get_symbols(self, arm32_elf_with_symbols: bytes) -> None:
        """Verify get_symbols returns parsed symbols."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm32_elf_with_symbols, "test_sym.elf")
        
        result = svc.get_symbols()
        
        assert result.total >= 2
        symbol_names = {s.name for s in result.symbols}
        assert "main" in symbol_names
    
    def test_symbol_search(self, arm32_elf_with_symbols: bytes) -> None:
        """Verify symbol search by name works."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm32_elf_with_symbols, "test_sym.elf")
        
        result = svc.get_symbols(query="main")
        
        assert len(result.symbols) >= 1
        assert result.symbols[0].name == "main"


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 5: Address Resolution
# ═══════════════════════════════════════════════════════════════════════════════

class TestAddressResolution:
    """Tests for resolving addresses to functions."""
    
    def test_resolve_address_in_function(
        self, arm32_elf_with_symbols: bytes
    ) -> None:
        """Resolve address within a known function."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm32_elf_with_symbols, "test_sym.elf")
        
        # main is at 0x08000100, size 12
        result = svc.resolve_address(0x08000104)
        
        assert result.address == 0x08000104
        assert result.function == "main"
        assert result.offset == 4
        assert result.instruction != ""  # Should have disassembly
    
    def test_resolve_address_unknown(self, arm32_elf: bytes) -> None:
        """Resolve address not in any function."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm32_elf, "test.elf")
        
        result = svc.resolve_address(0xDEADBEEF)
        
        assert result.address == 0xDEADBEEF
        assert result.function == "???"
    
    def test_resolve_nearby_context(self, arm32_elf: bytes) -> None:
        """Resolve should include nearby instructions for context."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm32_elf, "test.elf")
        
        result = svc.resolve_address(0x08000100)
        
        assert len(result.nearby) >= 1
        # First nearby should be the resolved address
        assert result.nearby[0].address == 0x08000100


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 6: Crash Address Extraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrashAddressExtraction:
    """Tests for extracting crash addresses from log lines."""
    
    def test_extract_pc_address(self, crash_log_lines: list[str]) -> None:
        """Extract PC address from kernel crash log."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        addrs = svc.extract_crash_addresses(crash_log_lines)
        
        assert len(addrs) >= 1
        # Should find 0x08000104 (PC)
        addr_values = [a[0] for a in addrs]
        assert 0x08000104 in addr_values
    
    def test_extract_rip_address(self, x86_crash_log: list[str]) -> None:
        """Extract RIP address from x86 crash log."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        addrs = svc.extract_crash_addresses(x86_crash_log)
        
        assert len(addrs) >= 1
        addr_values = [a[0] for a in addrs]
        assert 0xffffffffc0123456 in addr_values
    
    def test_extract_from_call_trace(self, crash_log_lines: list[str]) -> None:
        """Extract addresses from call trace lines."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        addrs = svc.extract_crash_addresses(crash_log_lines)
        
        # Should find multiple addresses from call trace
        assert len(addrs) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 7: Log Analysis
# ═══════════════════════════════════════════════════════════════════════════════

class TestLogAnalysis:
    """Tests for full log analysis with address correlation."""
    
    def test_analyze_logs_with_crash(
        self, arm32_elf_with_symbols: bytes, crash_log_lines: list[str]
    ) -> None:
        """Analyze crash logs and correlate with disassembly."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm32_elf_with_symbols, "test_sym.elf")
        
        result = svc.analyze_logs(crash_log_lines, device="cortex-a7")
        
        # Should find at least one anomaly
        assert len(result.anomalies) >= 1
        
        # Anomaly should have resolved address
        anomaly = result.anomalies[0]
        assert anomaly.address == 0x08000104
        assert anomaly.function == "main"
        assert anomaly.severity in ("CRITICAL", "WARNING", "INFO")
    
    def test_analyze_logs_no_binary(self, crash_log_lines: list[str]) -> None:
        """Analyze logs when no binary is loaded."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        result = svc.analyze_logs(crash_log_lines, device="test")
        
        # Should still extract addresses but not resolve
        assert len(result.resolved_addresses) >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 8: Service State Management
# ═══════════════════════════════════════════════════════════════════════════════

class TestServiceState:
    """Tests for service state management."""
    
    def test_get_meta_no_binary(self) -> None:
        """get_meta returns None when no binary loaded."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        assert svc.get_meta() is None
    
    def test_get_meta_after_load(self, arm32_elf: bytes) -> None:
        """get_meta returns metadata after loading."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm32_elf, "test.elf")
        
        meta = svc.get_meta()
        assert meta is not None
        assert meta.filename == "test.elf"
    
    def test_clear_service(self, arm32_elf: bytes) -> None:
        """Clear removes loaded binary."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm32_elf, "test.elf")
        assert svc.get_meta() is not None
        
        svc.clear()
        assert svc.get_meta() is None
    
    def test_load_replaces_previous(self, arm32_elf: bytes, arm64_elf: bytes) -> None:
        """Loading a new binary replaces the previous one."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        svc.load_binary(arm32_elf, "arm32.elf")
        assert svc.get_meta().arch == "arm"
        
        svc.load_binary(arm64_elf, "arm64.elf")
        assert svc.get_meta().arch == "arm64"


# ═══════════════════════════════════════════════════════════════════════════════
# Test Group 9: Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_empty_binary(self) -> None:
        """Empty binary should raise error."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        
        with pytest.raises(ValueError):
            svc.load_binary(b"", "empty.bin", arch="arm")
    
    def test_truncated_elf(self) -> None:
        """Truncated ELF should raise error."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        truncated = b"\x7fELF\x01\x01\x01\x00"  # Only 8 bytes
        
        with pytest.raises(ValueError, match="truncated"):
            svc.load_binary(truncated, "truncated.elf")
    
    def test_resolve_before_load(self) -> None:
        """Resolve before loading should return unknown."""
        from src.services.disasm_service import DisasmService
        
        svc = DisasmService()
        result = svc.resolve_address(0x12345678)
        
        assert result.function == "???"
