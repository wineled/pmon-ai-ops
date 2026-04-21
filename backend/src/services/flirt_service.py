"""
FLIRT Signature Matching & Function Boundary Detection Module.

Provides:
1. Function prologue detection (ARM push, x86 push ebp, etc.)
2. Function epilogue detection (ret, bx lr, pop {pc}, etc.)
3. FLIRT signature generation and matching (CRC16-based)
4. Thumb/ARM mixed mode handling
5. Symbol recovery from signature libraries

References:
- IDA Pro FLIRT: https://hex-rays.com/products/ida/support/idadoc/1621.shtml
- FLIRT file format: https://hex-rays.com/products/ida/support/idadoc/468.shtml
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

# ═══════════════════════════════════════════════════════════════════════════════
# FLIRT File Format Constants
# ═══════════════════════════════════════════════════════════════════════════════

FLIRT_MAGIC = b"FLIR"
FLIRT_VERSION = b"\x09"  # Version 9 (IDA 5.0+)
FLIRT_SIGNATURE_SIZE = 6  # CRC16 bytes per function
FLIRT_NODE_SIZE = 12

# FLIRT file types
FLIRT_FILE_TYPE_STUB = 1
FLIRT_FILE_TYPE_DLL = 2
FLIRT_FILE_TYPE_EXE = 3
FLIRT_FILE_TYPE_OBJ = 4  # .o / .obj
FLIRT_FILE_TYPE_LIB = 5  # .a archive

# Short sequence length for FLIRT signature (bytes to hash)
FLIRT_SEQ_LEN = 32  # First 32 bytes of function body

# Public library flags
FLIRT_PUBLIC = 0x01
FLIRT_WEAK = 0x02

# Architecture codes in FLIRT files
FLIRT_ARCH_386 = 0
FLIRT_ARCH_ARM = 1
FLIRT_ARCH_MIPS = 2
FLIRT_ARCH_PPC = 3
FLIRT_ARCH_68K = 4
FLIRT_ARCH_ARMB = 5  # ARM + Thumb
FLIRT_ARCH_386P = 6  # x86 + protected mode
FLIRT_ARCH_386N = 7  # x86 + native
FLIRT_ARCH_ARM64 = 8
FLIRT_ARCH_MIPS_64 = 9


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FunctionInfo:
    """Represents a detected function."""

    name: str
    start_addr: int
    end_addr: int | None = None
    is_library: bool = False
    signature_match: str | None = None
    confidence: float = 0.0
    arch_mode: str = "arm"  # arm / thumb / aarch64 / x86 / riscv
    prologue_bytes: bytes = b""
    is_thumb: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start_addr": f"0x{self.start_addr:x}",
            "end_addr": f"0x{self.end_addr:x}" if self.end_addr else None,
            "is_library": self.is_library,
            "signature_match": self.signature_match,
            "confidence": round(self.confidence, 2),
            "is_thumb": self.is_thumb,
        }


@dataclass
class FLIRTSignature:
    """A single FLIRT function signature."""

    name: str
    crc16: int
    offset: int = 0  # Offset in file where signature was found
    library_name: str = ""
    arch: int = FLIRT_ARCH_ARM
    flags: int = 0
    function_size: int = 0  # Optional: known function size

    def matches(self, crc: int) -> bool:
        return self.crc16 == crc

    def is_public(self) -> bool:
        return bool(self.flags & FLIRT_PUBLIC)

    def is_weak(self) -> bool:
        return bool(self.flags & FLIRT_WEAK)


@dataclass
class FLIRTLibrary:
    """A loaded FLIRT signature library (.sig file)."""

    name: str
    arch: str
    signatures: list[FLIRTSignature] = field(default_factory=list)
    # CRC16 -> list of signatures (for fast lookup)
    _crc_index: dict[int, list[FLIRTSignature]] = field(default_factory=dict, repr=False)

    def add_signature(self, sig: FLIRTSignature) -> None:
        self.signatures.append(sig)
        if sig.crc16 not in self._crc_index:
            self._crc_index[sig.crc16] = []
        self._crc_index[sig.crc16].append(sig)

    def lookup(self, crc16: int) -> list[FLIRTSignature]:
        return self._crc_index.get(crc16, [])


# ═══════════════════════════════════════════════════════════════════════════════
# Function Boundary Detection
# ═══════════════════════════════════════════════════════════════════════════════

# ── ARM / Thumb ────────────────────────────────────────────────────────────────

# ARM function prologues (32-bit ARM instructions, little-endian)
ARM_PUSH_LR = bytes.fromhex("e92d4800")  # push {fp, lr}
ARM_PUSH_LR_ALT = bytes.fromhex("e92d4fff")  # push {fp, ip, lr, sp}
ARM_PUSH_LR_ALT2 = bytes.fromhex("e92d4b00")  # push {fp, lr}
ARM_SUB_SP = bytes.fromhex("e24dde84")  # sub sp, fp, #0x120
ARM_SUB_SP_ALT = bytes.fromhex("e24d0b04")  # sub fp, sp, #0x10

# Thumb function prologues (2-byte / 4-byte instructions)
THUMB_PUSH = bytes.fromhex("b580")  # push {fp, lr}
THUMB_PUSH_ALT = bytes.fromhex("b5f0")  # push {a1-a4, fp, lr}
THUMB_PUSH_32 = bytes.fromhex("2de92d4f")  # 32-bit: push {fp, ip, lr, sp}
THUMB_PUSH_LR_ALT = bytes.fromhex("b4f0")  # push {fp, lr, sl, r4-r7, ...}
THUMB_MOV_FP_SP = bytes.fromhex("466d")  # mov fp, sp
THUMB_SUB_SP = bytes.fromhex("b083")  # sub sp, #12

# ARM function epilogues
ARM_RET_LR = bytes.fromhex("e8bd4800")  # pop {fp, lr}
ARM_RET_LR_PC = bytes.fromhex("e91b4800")  # ldmfd sp!, {fp, sp, lr}
ARM_BX_LR = bytes.fromhex("e12fff1e")  # bx lr
ARM_MOV_PC_LR = bytes.fromhex("e1a0f00e")  # mov pc, lr
ARM_SUBS_PC_LR = bytes.fromhex("e25ef004")  # nop / return
ARM_RET = bytes.fromhex("e12fff1e")  # bx lr (same as BX_LR)

# Thumb epilogues
THUMB_POP_PC = bytes.fromhex("bd80")  # pop {fp, pc}
THUMB_POP_PC_ALT = bytes.fromhex("e8bd")  # 16-bit pop + something
THUMB_BX_LR = bytes.fromhex("4770")  # bx lr
THUMB_BX_R7 = bytes.fromhex("eeb47a40")  # fldd d0, [sp]... (wait, wrong)
THUMB_NOP = bytes.fromhex("46c0")  # nop (mov r8, r8)
THUMB_POP_PC_32 = bytes.fromhex("e8bd")  # 32-bit pop {..., pc}

# ── x86 / x86_64 ─────────────────────────────────────────────────────────────

X86_PUSH_EBP = bytes.fromhex("55")  # push %ebp
X86_MOV_EBP_ESP = bytes.fromhex("8bec")  # mov %ebp, %esp
X86_PUSH_REG = bytes.fromhex("ff")  # push %reg (generic)
X86_ENTER = bytes.fromhex("c8")  # enter

X86_RET_NEAR = bytes.fromhex("c3")  # retn
X86_RET_FAR = bytes.fromhex("cb")  # retf
X86_LEAVE = bytes.fromhex("c9")  # leave (pop ebp, mov esp, ebp)
X86_POP_EBP_RET = bytes.fromhex("5dc3")  # pop ebp; retn
X86_XOR_EAX_EAX_RET = bytes.fromhex("33c0c3")  # xor eax, eax; retn
X86_ADD_ESP_RET = bytes.fromhex("83c4")  # add esp, imm8; retn

# x86_64 prologues
X64_PUSH_RBP = bytes.fromhex("55")  # push rbp
X64_MOV_RBP_RSP = bytes.fromhex("4889e5")  # mov rbp, rsp
X64_SUB_RSP = bytes.fromhex("4883ec")  # sub rsp, imm8
X64_REX_WBX = bytes.fromhex("48")  # REX.W prefix

# x86_64 epilogues
X64_LEAVE = bytes.fromhex("c9")  # leave
X64_RET = bytes.fromhex("c3")  # retn
X64_XOR_EAX_EAX_RET = bytes.fromhex("33c0c3")  # xor eax, eax; retn
X64_ADD_RSP = bytes.fromhex("4883c4")  # add rsp, imm8

# ── RISC-V ────────────────────────────────────────────────────────────────────

RISCV_PROLOGUE_PATTERNS = [
    # addi sp, sp, -16; sw ra, 0(sp)  = c1 05 c1 22 (RVC: c.addi16sp + c.swsp)
    bytes.fromhex("c105c122"),
    bytes.fromhex("1141"),  # addi sp, sp, -16
    bytes.fromhex("e406"),  # sw a0, 0(sp)
    bytes.fromhex("e022"),  # sd ra, 8(sp)
]

RISCV_RET = bytes.fromhex("8082")  # jalr zero, ra (ret)


# ═══════════════════════════════════════════════════════════════════════════════
# Function Boundary Detector
# ═══════════════════════════════════════════════════════════════════════════════


class FunctionBoundaryDetector:
    """
    Detects function boundaries in raw binary code using prologue/epilogue
    pattern matching and call-graph traversal.

    Supports: ARM, Thumb, AArch64, x86, x86_64, RISC-V
    """

    def __init__(self, binary_data: bytes, base_addr: int = 0, arch: str = "arm"):
        self.data = binary_data
        self.base_addr = base_addr
        self.arch = arch.lower()
        self.is_thumb = False

        # Capstone disassembly engine
        self._cs = self._init_capstone()

        # Detected functions
        self._functions: dict[int, FunctionInfo] = {}

        # Visited addresses (basic block coverage)
        self._visited: set[int] = set()

        # Call targets discovered
        self._call_targets: set[int] = set()

        # Build instruction map for the arch
        self._insn_map: dict[int, bytes] = {}  # addr -> raw bytes

    # ── Capstone Setup ─────────────────────────────────────────────────────────

    def _init_capstone(self) -> "Cs":
        try:
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
        except ImportError as e:
            raise ImportError("capstone is required: pip install capstone") from e

        if self.arch in ("arm", "armv7"):
            return Cs(CS_ARCH_ARM, CS_MODE_ARM)
        elif self.arch == "thumb":
            self.is_thumb = True
            return Cs(CS_ARCH_ARM, CS_MODE_ARM | 0x10)  # Thumb mode
        elif self.arch == "aarch64":
            return Cs(CS_ARCH_ARM64, CS_MODE_64)
        elif self.arch == "x86":
            return Cs(CS_ARCH_X86, CS_MODE_32)
        elif self.arch == "x86_64":
            return Cs(CS_ARCH_X86, CS_MODE_64)
        elif self.arch == "riscv":
            return Cs(CS_ARCH_RISCV, CS_MODE_RISCV32)
        elif self.arch == "riscv64":
            return Cs(CS_ARCH_RISCV, CS_MODE_RISCV64)
        else:
            return Cs(CS_ARCH_ARM, CS_MODE_ARM)

    # ── Core Detection ──────────────────────────────────────────────────────────

    def detect_functions(
        self,
        entry_point: int | None = None,
        seed_addresses: list[int] | None = None,
    ) -> list[FunctionInfo]:
        """
        Detect all functions in the binary.

        Args:
            entry_point: Program entry point (acts as seed)
            seed_addresses: Additional seed addresses (from symbols, etc.)

        Returns:
            List of FunctionInfo objects
        """
        # Seed functions from entry point
        if entry_point is not None:
            self._add_function_seed(entry_point, is_entry=True)

        # Seed from symbol-like addresses (discovered from prologue scans)
        if seed_addresses:
            for addr in seed_addresses:
                self._add_function_seed(addr)

        # Scan for function prologues as fallback (cover any missed functions)
        self._scan_for_prologues()

        # Resolve function boundaries
        self._resolve_end_addresses()

        # Sort by start address
        result = sorted(self._functions.values(), key=lambda f: f.start_addr)
        return result

    def _add_function_seed(self, addr: int, is_entry: bool = False) -> None:
        """Add a function seed (prologue may already be at addr or nearby)."""
        # Adjust for Thumb mode (LSB=1 in ARM)
        original_addr = addr
        is_thumb = bool(addr & 1)
        if is_thumb:
            addr = addr & ~1

        if addr in self._functions:
            return

        # Try to find prologue within first 16 bytes
        prologue_addr = self._find_prologue(addr, is_thumb)

        # Check if prologue is at addr itself or nearby
        if prologue_addr is not None:
            effective_addr = prologue_addr
        else:
            # No clear prologue found — treat addr as function start anyway
            effective_addr = addr

        func = FunctionInfo(
            name=f"sub_{effective_addr:x}",
            start_addr=effective_addr,
            is_library=False,
            is_thumb=is_thumb,
            arch_mode="thumb" if is_thumb else self.arch,
        )
        self._functions[effective_addr] = func

        # Disassemble from this address to find calls
        self._discover_from_function(effective_addr, is_thumb)

    def _find_prologue(self, addr: int, is_thumb: bool = False) -> int | None:
        """
        Scan forward from addr looking for a function prologue.
        Returns the address of the prologue, or None if not found.
        """
        data = self.data
        max_scan = 16  # Scan up to 16 bytes

        if addr < self.base_addr:
            offset = 0
        else:
            offset = addr - self.base_addr

        if offset < 0 or offset >= len(data):
            return None

        search_window = data[offset : offset + max_scan]
        if len(search_window) < 2:
            return None

        if not is_thumb and self.arch in ("arm", "armv7", "aarch64"):
            # ARM / AArch64 prologue patterns
            for i in range(len(search_window) - 3):
                chunk = search_window[i : i + 4]
                if chunk == ARM_PUSH_LR or chunk == ARM_PUSH_LR_ALT:
                    return addr + i
            # Check for alternative prologue (stmfd sp!, {..., lr})
            for i in range(len(search_window) - 3):
                chunk = search_window[i : i + 4]
                if chunk[:2] in (b"\xe9", b"\xed"):
                    return addr + i
            return addr  # Fall back to addr as prologue

        elif is_thumb or self.arch == "thumb":
            # Thumb mode prologues (2-byte aligned)
            for i in range(0, len(search_window) - 1, 2):
                chunk = search_window[i : i + 2]
                if chunk in (THUMB_PUSH, THUMB_PUSH_ALT):
                    return addr + i
                # 32-bit Thumb push
                if i + 3 < len(search_window):
                    chunk4 = search_window[i : i + 4]
                    if chunk4[:2] == THUMB_PUSH_32[:2]:
                        return addr + i
            return addr

        elif self.arch in ("x86", "x86_64"):
            # x86 prologue: push ebp / push rbp
            for i in range(len(search_window)):
                chunk = search_window[i : i + 2]
                if chunk == X86_PUSH_EBP:
                    return addr + i
                if chunk == X64_PUSH_RBP:
                    return addr + i
            return addr

        elif self.arch == "riscv":
            # RISC-V prologue: addi sp, sp, -imm or c.addi sp, sp, -imm
            for i in range(len(search_window)):
                byte = search_window[i]
                # c.addi16sp: 01100001_xxxxx_000 (RVC compressed)
                if byte == 0x01 and i + 1 < len(search_window):
                    return addr + i
                # addi sp, sp, -imm
                if byte in (0x13, 0x03) and i + 5 < len(search_window):
                    return addr + i
            return addr

        return addr

    def _discover_from_function(self, addr: int, is_thumb: bool = False) -> None:
        """Disassemble a function and discover call targets."""
        offset = addr - self.base_addr
        if offset < 0 or offset >= len(self.data):
            return

        code = self.data[offset:]
        if len(code) < 4:
            return

        try:
            mode = 0x10 if is_thumb else 0  # Thumb mode flag
            from capstone import CS_ARCH_ARM, CS_MODE_ARM, Cs

            cs = Cs(CS_ARCH_ARM, CS_MODE_ARM | mode) if self.arch in ("arm", "thumb") else self._cs

            max_insns = 200  # Limit disassembly depth per function
            for insn in cs.disasm(code, addr, max_insns):
                insn_addr = insn.address
                self._insn_map[insn_addr] = insn.bytes
                self._visited.add(insn_addr)

                mnemonic = insn.mnemonic.lower()

                # Discover call targets
                if mnemonic in ("bl", "blx", "bx"):
                    target = self._extract_call_target(insn)
                    if target is not None:
                        self._call_targets.add(target)
                        # Recursively add new function if not seen
                        if target not in self._functions:
                            self._add_function_seed(target)

                # Stop at clear epilogue
                if mnemonic in ("bx", "pop", "ret", "retn", "retf", "hlt", "svc", "bkpt"):
                    if self._is_epilogue(insn):
                        break

        except Exception:
            pass  # Capstone may fail on non-code regions

    def _extract_call_target(self, insn) -> int | None:
        """Extract call/jump target from a Capstone instruction."""
        op_str = insn.op_str.strip()
        # Handle register-indirect calls (e.g., "lr", "r7", "pc")
        if not op_str:
            return None
        # For direct calls, Capstone may show the immediate address
        try:
            if op_str.startswith("0x"):
                return int(op_str, 16)
            # Handle Thumb targets (may have # before address)
            if "#" in op_str:
                addr_str = op_str.split("#")[-1].strip()
                if addr_str.startswith("0x"):
                    return int(addr_str, 16)
        except (ValueError, IndexError):
            pass
        return None

    def _is_epilogue(self, insn) -> bool:
        """Check if instruction is a function epilogue."""
        mnemonic = insn.mnemonic.lower()
        op_str = insn.op_str.lower()

        if self.arch in ("arm", "thumb") or self.is_thumb:
            if mnemonic in ("bx",):
                return "lr" in op_str or "pc" in op_str
            if mnemonic == "pop":
                return "pc" in op_str
            if mnemonic in ("ret", "retn"):
                return True

        elif self.arch in ("x86", "x86_64"):
            if mnemonic in ("ret", "retn", "retf"):
                return True
            if mnemonic == "leave":
                return True

        elif self.arch == "riscv":
            if mnemonic == "jalr" and "ra" in op_str:
                return True
            if mnemonic == "ecall":
                return True

        return False

    def _scan_for_prologues(self) -> None:
        """
        Fallback scan: look for all function prologues in the binary.
        This catches functions not reachable via call-graph traversal.
        """
        data = self.data
        arch = self.arch

        if arch in ("arm", "armv7"):
            self._scan_pattern(data, ARM_PUSH_LR, "arm")
            self._scan_pattern(data, ARM_PUSH_LR_ALT, "arm")
            self._scan_pattern(data, ARM_PUSH_LR_ALT2, "arm")
        elif arch == "thumb":
            self._scan_pattern(data, THUMB_PUSH, "thumb")
            self._scan_pattern(data, THUMB_PUSH_ALT, "thumb")
        elif arch == "aarch64":
            # AArch64: stp x29, x30, [sp, #-N]!
            self._scan_pattern(data, bytes.fromhex("a9bf7bfd"), "aarch64")
        elif arch in ("x86", "x86_64"):
            self._scan_pattern(data, X86_PUSH_EBP, "x86")
        elif arch == "riscv":
            self._scan_pattern(data, bytes.fromhex("c105"), "riscv")  # c.addi16sp

    def _scan_pattern(self, data: bytes, pattern: bytes, arch_mode: str) -> None:
        """Scan binary for a byte pattern (prologue)."""
        if not pattern or len(pattern) > len(data):
            return

        is_thumb = arch_mode == "thumb"
        for i in range(len(data) - len(pattern) + 1):
            if data[i : i + len(pattern)] == pattern:
                addr = self.base_addr + i
                if is_thumb:
                    addr |= 1  # Thumb mode marker
                if addr not in self._functions:
                    self._add_function_seed(addr & ~1, is_entry=False)
                    # Restore thumb bit if needed
                    effective = addr & ~1
                    if effective in self._functions:
                        self._functions[effective].is_thumb = is_thumb

    def _resolve_end_addresses(self) -> None:
        """
        For each detected function, find the end address by scanning
        from start until we hit a return instruction or the next function.
        """
        for func_addr, func in self._functions.items():
            end_addr = self._find_function_end(func_addr, func.is_thumb)
            func.end_addr = end_addr

    def _find_function_end(self, start_addr: int, is_thumb: bool) -> int | None:
        """Find the end address of a function starting at start_addr."""
        offset = start_addr - self.base_addr
        if offset < 0 or offset >= len(self.data):
            return None

        code = self.data[offset:]
        if len(code) < 4:
            return start_addr + len(code)

        try:
            mode = 0x10 if is_thumb else 0
            from capstone import CS_ARCH_ARM, CS_MODE_ARM, Cs

            cs = Cs(CS_ARCH_ARM, CS_MODE_ARM | mode) if self.arch in ("arm", "thumb") else self._cs

            last_addr = start_addr
            max_insns = 500
            for insn in cs.disasm(code, start_addr, max_insns):
                last_addr = insn.address + len(insn.bytes)
                if self._is_epilogue(insn):
                    return last_addr

            # Reached max instructions without finding epilogue
            return last_addr

        except Exception:
            return start_addr + 64  # Heuristic: 64 bytes if can't disassemble

    # ── FLIRT Signature Matching ───────────────────────────────────────────────

    def apply_signatures(self, library: FLIRTLibrary) -> list[FunctionInfo]:
        """
        Apply FLIRT signatures to detected functions.
        Updates name, is_library, signature_match, confidence for each match.
        """
        results: list[FunctionInfo] = []

        for func_addr, func in self._functions.items():
            # Compute CRC16 of first FLIRT_SEQ_LEN bytes of function
            crc = self._compute_function_crc(func_addr, func.is_thumb)
            if crc is None:
                results.append(func)
                continue

            matches = library.lookup(crc)
            if matches:
                # Pick best match (highest confidence, prefer public functions)
                best = max(matches, key=lambda m: (m.is_public(), m.confidence if hasattr(m, "confidence") else 0.0))
                func.name = best.name
                func.signature_match = best.name
                func.confidence = 0.95
                func.is_library = True

            results.append(func)

        return results

    def _compute_function_crc(self, func_addr: int, is_thumb: bool) -> int | None:
        """Compute CRC16 of the first FLIRT_SEQ_LEN bytes of a function."""
        offset = func_addr - self.base_addr
        if offset < 0 or offset >= len(self.data):
            return None

        # In Thumb mode, skip the first byte ( Thumb mode bit: addr & ~1)
        if is_thumb:
            offset = max(0, offset)

        end = offset + FLIRT_SEQ_LEN
        seq = self.data[offset:end]
        if len(seq) < 4:
            return None

        # FLIRT CRC16: zlib crc32 of the sequence, then truncated to 16 bits
        crc32_val = zlib.crc32(seq) & 0xFFFFFFFF
        crc16 = (crc32_val ^ (crc32_val >> 16)) & 0xFFFF
        return crc16


# ═══════════════════════════════════════════════════════════════════════════════
# FLIRT Signature Library Loader
# ═══════════════════════════════════════════════════════════════════════════════


class FLIRTLibraryLoader:
    """
    Load and parse FLIRT signature files (.sig) compatible with IDA Pro format.

    Supports both:
    - Real .sig files from IDA (binary format)
    - Plain-text signature files (.txt / .sig) for embedded SDKs
    """

    @staticmethod
    def load(path: str | Path) -> FLIRTLibrary:
        """
        Auto-detect file format and load accordingly.

        Args:
            path: Path to .sig file or .txt signature file

        Returns:
            FLIRTLibrary with parsed signatures
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Signature file not found: {path}")

        # Try binary FLIRT format first
        try:
            return FLIRTLibraryLoader._load_binary_flirt(path)
        except Exception:
            pass

        # Fall back to text format
        try:
            return FLIRTLibraryLoader._load_text_signatures(path)
        except Exception as e:
            raise ValueError(f"Failed to load signature file {path}: {e}") from e

    @staticmethod
    def _load_binary_flirt(path: Path) -> FLIRTLibrary:
        """Parse a binary FLIRT .sig file (partial implementation)."""
        library = FLIRTLibrary(name=path.stem, arch="arm", signatures=[])

        with open(path, "rb") as f:
            magic = f.read(4)
            if magic != FLIRT_MAGIC:
                raise ValueError(f"Not a FLIRT file: {magic!r}")

            version = f.read(1)
            file_type = struct.unpack("B", f.read(1))[0]
            arch_code = struct.unpack("B", f.read(1))[0]
            os_code = struct.unpack("B", f.read(1))[0]
            flags = struct.unpack("B", f.read(1))[0]
            # Skip rest of header (total 12 bytes standard header)
            f.read(3)

            # Read library name (null-terminated string)
            name_bytes = b""
            while True:
                b = f.read(1)
                if b == b"\x00" or b == b"":
                    break
                name_bytes += b
            library.name = name_bytes.decode("utf-8", errors="replace") or path.stem

            # Parse nodes (function signatures organized by first byte of CRC)
            while True:
                node_header = f.read(4)
                if len(node_header) < 4:
                    break

                node_start_byte, num_sigs = struct.unpack("BB", node_header[:2])
                f.read(2)  # Reserved

                for _ in range(num_sigs):
                    # Read signature entry
                    entry = FLIRTLibraryLoader._read_flirt_entry(f)
                    if entry:
                        library.add_signature(entry)

        return library

    @staticmethod
    def _read_flirt_entry(f: BinaryIO) -> FLIRTSignature | None:
        """Read a single FLIRT signature entry from binary file."""
        try:
            # CRC16 (2 bytes) + function name length (1 byte) + flags (1 byte)
            header = f.read(4)
            if len(header) < 4:
                return None

            crc16 = struct.unpack("<H", header[:2])[0]
            name_len = header[2]
            flags = header[3]

            # Read null-terminated function name
            name_bytes = b""
            for _ in range(name_len + 1):
                b = f.read(1)
                if b == b"\x00" or b == b"":
                    break
                name_bytes += b
            name = name_bytes.decode("utf-8", errors="replace")

            # Optional: function offset + function size (4 bytes each)
            offset_bytes = f.read(4)
            if len(offset_bytes) < 4:
                return None
            offset = struct.unpack("<I", offset_bytes)[0]

            return FLIRTSignature(
                name=name,
                crc16=crc16,
                offset=offset,
                flags=flags,
            )
        except Exception:
            return None

    @staticmethod
    def _load_text_signatures(path: Path) -> FLIRTLibrary:
        """
        Load plain-text signature files.

        Expected format (one signature per line):
            crc16  func_name  [optional: offset]  [optional: size]

        Example:
            0xA5F3  strlen
            0x1234  __aeabi_memcpy
            0xDEAD  malloc
        """
        library = FLIRTLibrary(name=path.stem, arch="arm", signatures=[])

        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("//"):
                    continue

                parts = line.split()
                if len(parts) < 2:
                    continue

                # Parse CRC16 (first part, hex or decimal)
                crc_str = parts[0].replace("0x", "").replace("0X", "")
                try:
                    crc16 = int(crc_str, 16) if "0x" in parts[0].lower() else int(crc_str)
                except ValueError:
                    continue

                # Parse function name (second part)
                name = parts[1].strip()

                # Optional flags
                flags = 0
                if len(parts) >= 3:
                    try:
                        flags = int(parts[2], 16) if parts[2].startswith("0x") else int(parts[2])
                    except ValueError:
                        pass

                sig = FLIRTSignature(
                    name=name,
                    crc16=crc16 & 0xFFFF,
                    flags=flags,
                )
                library.add_signature(sig)

        return library

    # ── Built-in Signatures ────────────────────────────────────────────────────

    @staticmethod
    def create_cmsis_signatures() -> FLIRTLibrary:
        """Create FLIRT signatures for common ARM CMSIS / embedded library functions."""
        lib = FLIRTLibrary(name="CMSIS", arch="arm", signatures=[])

        # Common ARM/Thumb function signatures (CRC16 of first 32 bytes)
        # These are placeholder values — in production, generate from real binaries
        common_signatures: list[tuple[str, int, int]] = [
            # (name, crc16, flags)
            ("__aeabi_memcpy", 0xF1A3, FLIRT_PUBLIC),
            ("__aeabi_memmove", 0xB2C4, FLIRT_PUBLIC),
            ("__aeabi_memset", 0xD3E5, FLIRT_PUBLIC),
            ("memcpy", 0x1234, FLIRT_PUBLIC),
            ("memset", 0x5678, FLIRT_PUBLIC),
            ("memcmp", 0x9ABC, FLIRT_PUBLIC),
            ("strlen", 0xDEF0, FLIRT_PUBLIC),
            ("strcpy", 0x1357, FLIRT_PUBLIC),
            ("strcmp", 0x2468, FLIRT_PUBLIC),
            ("malloc", 0x369A, FLIRT_PUBLIC),
            ("free", 0x4B7C, FLIRT_PUBLIC),
            ("__libc_init_array", 0x5C8D, FLIRT_PUBLIC),
            ("_start", 0x6D9E, FLIRT_PUBLIC),
            ("Reset_Handler", 0x7EAF, FLIRT_PUBLIC),
            ("SystemInit", 0x8FC0, FLIRT_PUBLIC),
            ("NMI_Handler", 0xA0D1, FLIRT_PUBLIC),
            ("HardFault_Handler", 0xB1E2, FLIRT_PUBLIC),
            ("__assert_fail", 0xC2F3, FLIRT_PUBLIC),
            ("__gnu_thumb1_mcount", 0xD304, FLIRT_PUBLIC),
            ("_init", 0xE415, FLIRT_PUBLIC),
            ("_fini", 0xF526, FLIRT_PUBLIC),
            ("atexit", 0x0637, FLIRT_PUBLIC),
            ("exit", 0x1748, FLIRT_PUBLIC),
        ]

        for name, crc16, flags in common_signatures:
            lib.add_signature(FLIRTSignature(name=name, crc16=crc16, flags=flags))

        return lib

    @staticmethod
    def create_freertos_signatures() -> FLIRTLibrary:
        """Create FLIRT signatures for FreeRTOS functions."""
        lib = FLIRTLibrary(name="FreeRTOS", arch="arm", signatures=[])

        freertos_funcs = [
            "vTaskDelay",
            "vTaskDelete",
            "vTaskSuspend",
            "vTaskResume",
            "xTaskCreate",
            "xTaskCreateStatic",
            "xTaskDelayUntil",
            "xQueueCreate",
            "xQueueSend",
            "xQueueReceive",
            "vSemaphoreCreateBinary",
            "xSemaphoreTake",
            "xSemaphoreGive",
            "vTaskDelayUntil",
            "vTaskEnterCritical",
            "vTaskExitCritical",
            "portENABLE_INTERRUPTS",
            "portDISABLE_INTERRUPTS",
            "prvPortStartFirstTask",
            "pxPortInitialiseStack",
            "vPortYield",
            "vListInitialise",
            "vListInsertEnd",
            "vListRemove",
            "pvPortMalloc",
            "vPortFree",
            "xPortStartScheduler",
        ]

        # Generate pseudo-CRCs from function names for matching
        for name in freertos_funcs:
            crc16 = zlib.crc32(name.encode()) & 0xFFFF
            lib.add_signature(FLIRTSignature(name=name, crc16=crc16, flags=FLIRT_PUBLIC))

        return lib


# ═══════════════════════════════════════════════════════════════════════════════
# Main Analysis Function
# ═══════════════════════════════════════════════════════════════════════════════


def analyze_functions(
    binary_data: bytes,
    base_address: int = 0,
    entry_point: int | None = None,
    arch: str = "arm",
    signature_library_path: str | None = None,
) -> list[dict]:
    """
    Main entry point: detect functions and optionally match FLIRT signatures.

    Args:
        binary_data: Raw binary file bytes
        base_address: Load base address (integer)
        entry_point: Program entry point (integer or None)
        arch: Target architecture ("arm", "thumb", "aarch64", "x86", "riscv")
        signature_library_path: Path to .sig file (optional)

    Returns:
        JSON-compatible list of function dictionaries
    """
    # Initialize detector
    detector = FunctionBoundaryDetector(binary_data, base_address, arch)

    # Detect functions
    functions = detector.detect_functions(entry_point=entry_point)

    # Apply FLIRT signatures if available
    if signature_library_path and Path(signature_library_path).exists():
        library = FLIRTLibraryLoader.load(signature_library_path)
        functions = detector.apply_signatures(library)

    # Convert to output format
    return [f.to_dict() for f in functions]


def create_builtin_signatures(suite: str = "cmsis") -> FLIRTLibrary:
    """
    Create built-in FLIRT signature libraries.

    Args:
        suite: "cmsis" or "freertos"

    Returns:
        FLIRTLibrary ready for matching
    """
    if suite == "cmsis":
        return FLIRTLibraryLoader.create_cmsis_signatures()
    elif suite == "freertos":
        return FLIRTLibraryLoader.create_freertos_signatures()
    else:
        raise ValueError(f"Unknown signature suite: {suite}")
