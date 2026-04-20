"""
Disassembly Service: ELF parsing, Capstone disassembly, and address resolution.

This service provides:
1. ELF binary parsing (architecture detection, symbol table extraction)
2. Raw binary loading with explicit architecture
3. Capstone-based disassembly
4. Address-to-function resolution
5. Crash log address extraction and correlation
"""

from __future__ import annotations

import re
import struct
import uuid

from capstone import (
    CS_ARCH_ARM,
    CS_ARCH_ARM64,
    CS_ARCH_RISCV,
    CS_ARCH_X86,
    CS_MODE_32,
    CS_MODE_64,
    CS_MODE_ARM,
    CS_MODE_RISCV32,
    CS_MODE_RISCV64,
    Cs,
)

from ..schemas.disasm import (
    AddressResolveResult,
    AnalysisResponse,
    BinFileMeta,
    DisasmLine,
    DisasmPageResponse,
    LogAnomaly,
    SymbolEntry,
    SymbolPageResponse,
)
from ..utils.logger import logger

# ═══════════════════════════════════════════════════════════════════════════════
# ELF Constants
# ═══════════════════════════════════════════════════════════════════════════════

ELF_MAGIC = b"\x7fELF"

# e_machine values
EM_386 = 3
EM_ARM = 40
EM_X86_64 = 62
EM_AARCH64 = 183
EM_RISCV = 243

# Section types
SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3

# Symbol types (st_info & 0xf)
STT_FUNC = 2
STT_OBJECT = 1

# Symbol binding (st_info >> 4)
STB_GLOBAL = 1
STB_LOCAL = 0


# ═══════════════════════════════════════════════════════════════════════════════
# Crash Address Regex Patterns
# ═══════════════════════════════════════════════════════════════════════════════

# PC/RIP patterns
PC_PATTERNS = [
    re.compile(r"PC is at\s+(0x[0-9a-fA-F]+)", re.IGNORECASE),
    re.compile(r"RIP:\s*(?:0010:.*?)?\s*(0x[0-9a-fA-F]+)", re.IGNORECASE),
    re.compile(r"pc\s*[:=]\s*\[?<?(0x[0-9a-fA-F]+)>?\]?", re.IGNORECASE),
    re.compile(r"LR\s*[:=]\s*\[?<?(0x[0-9a-fA-F]+)>?\]?", re.IGNORECASE),
    re.compile(r"at\s+(?:address\s+)?(0x[0-9a-fA-F]+)", re.IGNORECASE),
    re.compile(r"from\s+(0x[0-9a-fA-F]+)", re.IGNORECASE),
    re.compile(r"\[<(0x[0-9a-fA-F]+)>\]", re.IGNORECASE),
    re.compile(r"\[<(0x[0-9a-fA-F]+)>\]", re.IGNORECASE),
    re.compile(r"<(0x[0-9a-fA-F]+)>", re.IGNORECASE),
]


# ═══════════════════════════════════════════════════════════════════════════════
# DisasmService Class
# ═══════════════════════════════════════════════════════════════════════════════

class DisasmService:
    """
    Singleton service for binary analysis and disassembly.

    Provides:
    - ELF parsing and architecture detection
    - Capstone-based disassembly
    - Symbol table parsing
    - Address resolution
    - Crash log analysis
    """

    def __init__(self) -> None:
        self._meta: BinFileMeta | None = None
        self._symbols: list[SymbolEntry] = []
        self._disasm_lines: list[DisasmLine] = []

        # Sorted symbol index for fast lookup: [(address, name, size), ...]
        self._symbol_index: list[tuple[int, str, int]] = []

        # Disassembly address map: {address: index in _disasm_lines}
        self._disasm_map: dict[int, int] = {}

        # Raw binary data
        self._raw_data: bytes = b""
        self._base_addr: int = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def load_binary(
        self,
        data: bytes,
        filename: str,
        arch: str = "auto",
        base_addr: int = 0,
    ) -> BinFileMeta:
        """
        Load a binary file (ELF or raw) for analysis.

        Args:
            data: Binary file contents
            filename: Original filename
            arch: Architecture ("auto" for ELF detection, or "arm"/"arm64"/"riscv"/"x86"/"x86_64")
            base_addr: Base address for raw binaries

        Returns:
            BinFileMeta with file information

        Raises:
            ValueError: If binary is invalid or architecture is unsupported
        """
        # Clear previous state
        self.clear()

        if len(data) == 0:
            raise ValueError("Empty binary file")

        self._raw_data = data

        # Detect ELF vs raw binary
        is_elf = data[:4] == ELF_MAGIC

        if is_elf:
            elf_info = self._parse_elf(data)
            arch = elf_info["arch"]
            bits = elf_info["bits"]
            entry = elf_info["entry"]
            base_addr = 0  # For ELF, addresses are absolute
            self._symbols = elf_info["symbols"]
            self._build_symbol_index()

            # Find code section for disassembly
            code_data = elf_info.get("code_section", data)
            code_vaddr = elf_info.get("code_vaddr", 0)

        elif arch == "auto":
            raise ValueError("Not an ELF file: specify architecture explicitly")
        else:
            # Raw binary with explicit architecture
            arch_map = {
                "arm": ("arm", 32),
                "arm64": ("arm64", 64),
                "riscv": ("riscv", 32),
                "x86": ("x86", 32),
                "x86_64": ("x86_64", 64),
            }
            if arch not in arch_map:
                raise ValueError(f"Unsupported architecture: {arch}")
            arch, bits = arch_map[arch]
            entry = base_addr
            code_data = data
            code_vaddr = base_addr

        # Disassemble
        self._disasm_lines = self._disassemble(
            code_data,
            code_vaddr,
            arch,
            bits,
        )
        self._build_disasm_map()

        # Build metadata
        self._meta = BinFileMeta(
            file_id=str(uuid.uuid4())[:8],
            filename=filename,
            size_bytes=len(data),
            arch=arch,
            bits=bits,
            entry_point=entry if is_elf else base_addr,
            is_elf=is_elf,
            section_count=elf_info.get("section_count", 0) if is_elf else 0,
            symbol_count=len(self._symbols),
            disasm_lines=len(self._disasm_lines),
        )

        self._base_addr = base_addr

        logger.info(
            f"[Disasm] Loaded {filename}: arch={arch}, bits={bits}, "
            f"symbols={len(self._symbols)}, disasm={len(self._disasm_lines)}"
        )

        return self._meta

    def get_meta(self) -> BinFileMeta | None:
        """Get metadata for loaded binary, or None if not loaded."""
        return self._meta

    def get_disassembly(
        self,
        offset: int = 0,
        limit: int = 500,
    ) -> DisasmPageResponse:
        """Get paginated disassembly results."""
        if not self._disasm_lines:
            return DisasmPageResponse(total=0, offset=0, limit=limit, lines=[])

        total = len(self._disasm_lines)
        lines = self._disasm_lines[offset : offset + limit]

        return DisasmPageResponse(
            total=total,
            offset=offset,
            limit=limit,
            lines=lines,
        )

    def get_symbols(
        self,
        query: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> SymbolPageResponse:
        """Get paginated symbol list, optionally filtered by name."""
        symbols = self._symbols

        if query:
            query_lower = query.lower()
            symbols = [s for s in symbols if query_lower in s.name.lower()]

        total = len(symbols)
        symbols = symbols[offset : offset + limit]

        return SymbolPageResponse(
            total=total,
            offset=offset,
            limit=limit,
            symbols=symbols,
        )

    def resolve_address(self, addr: int) -> AddressResolveResult:
        """
        Resolve an address to its containing function and instruction.

        Args:
            addr: Address to resolve

        Returns:
            AddressResolveResult with function name, offset, and instruction
        """
        if not self._meta:
            return AddressResolveResult(address=addr, function="???")

        # Find containing function
        func_name, func_offset = self._find_function(addr)

        # Find instruction at address
        instruction = ""
        nearby: list[DisasmLine] = []

        # Try exact match first
        idx = self._disasm_map.get(addr)

        # If not found, find the closest instruction whose start <= addr
        # (handles x86 variable-length instructions where crash addr may
        #  land in the middle of a multi-byte instruction)
        if idx is None and self._disasm_lines:
            import bisect
            line_addrs = [line.address for line in self._disasm_lines]
            pos = bisect.bisect_right(line_addrs, addr) - 1
            if pos >= 0:
                candidate = self._disasm_lines[pos]
                byte_len = len(bytes.fromhex(candidate.bytes_hex)) if candidate.bytes_hex else 0
                if candidate.address <= addr < candidate.address + byte_len:
                    idx = pos

        if idx is not None:
            line = self._disasm_lines[idx]
            instruction = f"{line.mnemonic} {line.op_str}".strip()

            # Get nearby instructions (2 before, 2 after)
            start = max(0, idx - 2)
            end = min(len(self._disasm_lines), idx + 3)
            nearby = self._disasm_lines[start:end]

        return AddressResolveResult(
            address=addr,
            function=func_name,
            offset=func_offset,
            instruction=instruction,
            nearby=nearby,
        )

    def extract_crash_addresses(
        self,
        log_lines: list[str],
    ) -> list[tuple[int, str]]:
        """
        Extract crash addresses from log lines.

        Args:
            log_lines: Log lines to parse

        Returns:
            List of (address, source_line) tuples
        """
        addresses: list[tuple[int, str]] = []
        seen: set[int] = set()

        for line in log_lines:
            for pattern in PC_PATTERNS:
                for match in pattern.finditer(line):
                    try:
                        addr = int(match.group(1), 16)
                        if addr not in seen:
                            seen.add(addr)
                            addresses.append((addr, line.strip()))
                    except ValueError:
                        continue

        return addresses

    def analyze_logs(
        self,
        log_lines: list[str],
        device: str = "unknown",
    ) -> AnalysisResponse:
        """
        Analyze crash logs and correlate with loaded binary.

        Args:
            log_lines: Log lines to analyze
            device: Device identifier

        Returns:
            AnalysisResponse with anomalies and resolved addresses
        """
        # Extract addresses
        addresses = self.extract_crash_addresses(log_lines)

        # Resolve addresses
        resolved: list[AddressResolveResult] = []
        anomalies: list[LogAnomaly] = []

        for addr, source_line in addresses:
            result = self.resolve_address(addr)
            resolved.append(result)

            # Create anomaly if we found a function OR nearby instructions
            if result.function != "???" or result.nearby:
                func_display = result.function if result.function != "???" else f"0x{addr:x}"
                anomaly = LogAnomaly(
                    severity="CRITICAL" if "fault" in source_line.lower() else "WARNING",
                    address=addr,
                    function=result.function,
                    description=f"Crash at {func_display}+0x{result.offset:x}",
                    log_line=source_line,
                    resolved=result,
                )
                anomalies.append(anomaly)

        return AnalysisResponse(
            anomalies=anomalies,
            resolved_addresses=resolved,
        )

    def clear(self) -> None:
        """Clear loaded binary and all cached data."""
        self._meta = None
        self._symbols.clear()
        self._disasm_lines.clear()
        self._symbol_index.clear()
        self._disasm_map.clear()
        self._raw_data = b""
        self._base_addr = 0

    # ── Private Helpers ───────────────────────────────────────────────────────

    def _parse_elf(self, data: bytes) -> dict:
        """Parse ELF header and extract metadata."""
        if len(data) < 52:
            raise ValueError("truncated ELF file")

        # Parse e_ident
        ei_class = data[4]  # 1=32-bit, 2=64-bit
        ei_data = data[5]   # 1=little-endian, 2=big-endian

        is_64bit = ei_class == 2
        is_little = ei_data == 1

        endian = "<" if is_little else ">"

        # Parse ELF header
        if is_64bit:
            if len(data) < 64:
                raise ValueError("truncated ELF file")
            # 64-bit header
            e_machine = struct.unpack(f"{endian}H", data[18:20])[0]
            e_entry = struct.unpack(f"{endian}Q", data[24:32])[0]
            e_shoff = struct.unpack(f"{endian}Q", data[40:48])[0]
            e_shentsize = struct.unpack(f"{endian}H", data[58:60])[0]
            e_shnum = struct.unpack(f"{endian}H", data[60:62])[0]
            e_shstrndx = struct.unpack(f"{endian}H", data[62:64])[0]
        else:
            # 32-bit header
            e_machine = struct.unpack(f"{endian}H", data[18:20])[0]
            e_entry = struct.unpack(f"{endian}I", data[24:28])[0]
            e_shoff = struct.unpack(f"{endian}I", data[32:36])[0]
            e_shentsize = struct.unpack(f"{endian}H", data[46:48])[0]
            e_shnum = struct.unpack(f"{endian}H", data[48:50])[0]
            e_shstrndx = struct.unpack(f"{endian}H", data[50:52])[0]

        # Detect architecture
        arch_map = {
            EM_ARM: "arm",
            EM_AARCH64: "arm64",
            EM_RISCV: "riscv",
            EM_386: "x86",
            EM_X86_64: "x86_64",
        }
        arch = arch_map.get(e_machine, "unknown")
        bits = 64 if is_64bit else 32

        # Parse section headers
        sections: list[dict] = []
        shstrtab_offset = 0

        for i in range(e_shnum):
            sh_offset = e_shoff + i * e_shentsize

            if is_64bit:
                sh_name = struct.unpack(f"{endian}I", data[sh_offset:sh_offset+4])[0]
                sh_type = struct.unpack(f"{endian}I", data[sh_offset+4:sh_offset+8])[0]
                sh_addr = struct.unpack(f"{endian}Q", data[sh_offset+16:sh_offset+24])[0]
                sh_off = struct.unpack(f"{endian}Q", data[sh_offset+24:sh_offset+32])[0]
                sh_size = struct.unpack(f"{endian}Q", data[sh_offset+32:sh_offset+40])[0]
                sh_link = struct.unpack(f"{endian}I", data[sh_offset+40:sh_offset+44])[0]
            else:
                sh_name = struct.unpack(f"{endian}I", data[sh_offset:sh_offset+4])[0]
                sh_type = struct.unpack(f"{endian}I", data[sh_offset+4:sh_offset+8])[0]
                sh_addr = struct.unpack(f"{endian}I", data[sh_offset+12:sh_offset+16])[0]
                sh_off = struct.unpack(f"{endian}I", data[sh_offset+16:sh_offset+20])[0]
                sh_size = struct.unpack(f"{endian}I", data[sh_offset+20:sh_offset+24])[0]
                sh_link = struct.unpack(f"{endian}I", data[sh_offset+24:sh_offset+28])[0]

            sections.append({
                "name_offset": sh_name,
                "type": sh_type,
                "addr": sh_addr,
                "offset": sh_off,
                "size": sh_size,
                "link": sh_link,
            })

            if i == e_shstrndx:
                shstrtab_offset = sh_off

        # Read section names
        def get_section_name(name_offset: int) -> str:
            end = data.find(b"\x00", shstrtab_offset + name_offset)
            if end == -1:
                return ""
            return data[shstrtab_offset + name_offset : end].decode("utf-8", errors="replace")

        for sec in sections:
            sec["name"] = get_section_name(sec["name_offset"])

        # Find .text section
        code_section = None
        code_offset = 0
        for sec in sections:
            if sec["name"] == ".text":
                code_section = data[sec["offset"] : sec["offset"] + sec["size"]]
                code_offset = sec["addr"]
                break

        # Parse symbol table
        symbols: list[SymbolEntry] = []
        symtab = None
        strtab = None

        for sec in sections:
            if sec["name"] == ".symtab":
                symtab = sec
            elif sec["name"] == ".strtab":
                strtab = sec

        if symtab and strtab:
            sym_data = data[symtab["offset"] : symtab["offset"] + symtab["size"]]
            str_data = data[strtab["offset"] : strtab["offset"] + strtab["size"]]

            sym_size = 24 if is_64bit else 16
            num_syms = len(sym_data) // sym_size

            for i in range(num_syms):
                sym_off = i * sym_size

                if is_64bit:
                    st_name = struct.unpack(f"{endian}I", sym_data[sym_off:sym_off+4])[0]
                    st_value = struct.unpack(f"{endian}Q", sym_data[sym_off+8:sym_off+16])[0]
                    st_size = struct.unpack(f"{endian}Q", sym_data[sym_off+16:sym_off+24])[0]
                    st_info = sym_data[sym_off+4]
                else:
                    st_name = struct.unpack(f"{endian}I", sym_data[sym_off:sym_off+4])[0]
                    st_value = struct.unpack(f"{endian}I", sym_data[sym_off+4:sym_off+8])[0]
                    st_size = struct.unpack(f"{endian}I", sym_data[sym_off+8:sym_off+12])[0]
                    st_info = sym_data[sym_off+12]

                # Get symbol name
                name_end = str_data.find(b"\x00", st_name)
                if name_end == -1:
                    name_end = len(str_data)
                name = str_data[st_name:name_end].decode("utf-8", errors="replace")

                # Only include functions
                sym_type = st_info & 0xf
                if sym_type == STT_FUNC and name and st_value:
                    symbols.append(SymbolEntry(
                        name=name,
                        address=st_value,
                        size=st_size,
                        sym_type="func",
                        section=".text",
                    ))

        return {
            "arch": arch,
            "bits": bits,
            "entry": e_entry,
            "section_count": len(sections),
            "symbols": symbols,
            "code_section": code_section,
            "code_vaddr": code_offset,  # Virtual address of code section
        }

    def _disassemble(
        self,
        code: bytes,
        base_addr: int,
        arch: str,
        bits: int,
    ) -> list[DisasmLine]:
        """Disassemble code using Capstone."""
        if not code:
            return []

        # Setup Capstone
        cs: Cs | None = None

        if arch == "arm":
            cs = Cs(CS_ARCH_ARM, CS_MODE_ARM)
        elif arch == "arm64":
            cs = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
        elif arch == "riscv":
            cs = Cs(CS_ARCH_RISCV, CS_MODE_RISCV32 if bits == 32 else CS_MODE_RISCV64)
        elif arch == "x86":
            cs = Cs(CS_ARCH_X86, CS_MODE_32)
        elif arch == "x86_64":
            cs = Cs(CS_ARCH_X86, CS_MODE_64)
        else:
            logger.warning(f"[Disasm] Unknown architecture: {arch}")
            return []

        cs.detail = False

        lines: list[DisasmLine] = []

        for insn in cs.disasm(code, base_addr):
            # Find containing function
            func_name, func_offset = self._find_function(insn.address)

            lines.append(DisasmLine(
                address=insn.address,
                bytes_hex=insn.bytes.hex(),
                mnemonic=insn.mnemonic,
                op_str=insn.op_str,
                function=func_name,
                offset_in_func=func_offset,
            ))

        return lines

    def _build_symbol_index(self) -> None:
        """Build sorted index for fast function lookup."""
        self._symbol_index = [
            (s.address, s.name, s.size)
            for s in self._symbols
            if s.size > 0
        ]
        self._symbol_index.sort(key=lambda x: x[0])

    def _build_disasm_map(self) -> None:
        """Build address-to-index map for fast lookup."""
        self._disasm_map = {
            line.address: idx
            for idx, line in enumerate(self._disasm_lines)
        }

    def _find_function(self, addr: int) -> tuple[str, int]:
        """
        Find the function containing an address.

        Returns:
            (function_name, offset_in_function)
        """
        if not self._symbol_index:
            return ("???", 0)

        # Extract just addresses for binary search (avoid tuple comparison issues)
        addresses = [item[0] for item in self._symbol_index]

        # Find rightmost function whose start address <= addr
        import bisect
        pos = bisect.bisect_right(addresses, addr) - 1

        if pos < 0:
            return ("???", 0)

        func_addr, func_name, func_size = self._symbol_index[pos]

        if func_addr <= addr < func_addr + func_size:
            return (func_name, addr - func_addr)

        return ("???", 0)


# Singleton instance
disasm_service = DisasmService()
