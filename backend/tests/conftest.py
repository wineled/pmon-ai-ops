"""
Test fixtures for disasm module TDD tests.
Provides minimal ELF binary generators and service fixtures.
"""

from __future__ import annotations

import struct
from typing import Generator

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# ELF Binary Generators
# ═══════════════════════════════════════════════════════════════════════════════

def make_minimal_arm32_elf(
    entry: int = 0x08000100,
    code: bytes | None = None,
    symbols: list[tuple[str, int, int]] | None = None,
) -> bytes:
    """
    Create a minimal 32-bit ARM ELF binary.
    
    Args:
        entry: Entry point address
        code: Raw ARM instructions (default: simple push/mov/pop)
        symbols: List of (name, address, size) for function symbols
    
    Returns:
        Complete ELF binary as bytes
    """
    # Default ARM code: push {r4,lr}, mov r4,#0, pop {r4,pc}
    if code is None:
        code = bytes([
            0x10, 0x40, 0x2d, 0xe9,  # push {r4, lr}
            0x00, 0x40, 0xa0, 0xe3,  # mov r4, #0
            0x10, 0x40, 0xbd, 0xe8,  # pop {r4, pc}
        ])
    
    has_symbols = symbols is not None and len(symbols) > 0
    
    # ── Calculate all offsets first ──────────────────────────────────────────
    elf_header_size = 52
    
    # .text section: right after ELF header
    text_offset = elf_header_size
    text_size = len(code)
    
    # Pad to 0x100 for shstrtab
    shstrtab_offset = 0x100
    shstrtab = b"\x00.text\x00.shstrtab\x00.symtab\x00.strtab\x00"
    shstrtab_size = len(shstrtab)
    
    # Symbol table and string table
    symtab_offset = 0
    symtab_size = 0
    strtab_offset = 0
    strtab_size = 0
    symtab_data = b""
    strtab_data = b""
    
    if has_symbols:
        # Build symbol table and string table
        strtab_data = b"\x00"
        symtab_parts = []
        
        # NULL symbol
        symtab_parts.append(struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0))
        
        for name, addr, size in symbols:
            st_name = len(strtab_data)
            strtab_data += name.encode() + b"\x00"
            # st_info = (STB_GLOBAL << 4) | STT_FUNC = (1 << 4) | 2 = 0x12
            symtab_parts.append(struct.pack("<IIIBBH", st_name, addr, size, 0x12, 0, 1))
        
        symtab_data = b"".join(symtab_parts)
        symtab_size = len(symtab_data)
        strtab_size = len(strtab_data)
        
        symtab_offset = shstrtab_offset + shstrtab_size
        strtab_offset = symtab_offset + symtab_size
    
    # Section header table
    sht_offset = shstrtab_offset + shstrtab_size
    if has_symbols:
        sht_offset = strtab_offset + strtab_size
    sht_offset = (sht_offset + 3) & ~3  # Align to 4
    
    # Number of sections
    shnum = 5 if has_symbols else 3
    shstrndx = 2  # .shstrtab is always section 2
    
    # ── Build ELF header ─────────────────────────────────────────────────────
    elf_header = struct.pack(
        "<16sHHIIIIIHHHHHH",
        b"\x7fELF\x01\x01\x01\x00" + b"\x00" * 8,  # e_ident
        2,              # e_type: ET_EXEC
        40,             # e_machine: EM_ARM
        1,              # e_version
        entry,          # e_entry
        0,              # e_phoff
        sht_offset,     # e_shoff
        0x5000200,      # e_flags: ARM EABI
        52,             # e_ehsize
        0,              # e_phentsize
        0,              # e_phnum
        40,             # e_shentsize
        shnum,          # e_shnum
        shstrndx,       # e_shstrndx
    )
    
    # ── Build section headers ────────────────────────────────────────────────
    # [0] NULL section
    sh_null = struct.pack("<IIIIIIIIII", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    
    # [1] .text section
    sh_text = struct.pack(
        "<IIIIIIIIII",
        1,              # sh_name: offset in shstrtab
        1,              # sh_type: SHT_PROGBITS
        6,              # sh_flags: SHF_ALLOC | SHF_EXECINSTR
        entry,          # sh_addr
        text_offset,    # sh_offset
        text_size,      # sh_size
        0, 0, 4, 0,     # sh_link, sh_info, sh_addralign, sh_entsize
    )
    
    # [2] .shstrtab section
    sh_shstrtab = struct.pack(
        "<IIIIIIIIII",
        7,              # sh_name: ".shstrtab" offset
        3,              # sh_type: SHT_STRTAB
        0, 0,           # sh_flags, sh_addr
        shstrtab_offset,# sh_offset
        shstrtab_size,  # sh_size
        0, 0, 1, 0,     # sh_link, sh_info, sh_addralign, sh_entsize
    )
    
    # ── Build the binary ─────────────────────────────────────────────────────
    binary = bytearray()
    binary.extend(elf_header)       # 0x00 - 0x34
    binary.extend(code)             # 0x34 - ...
    
    # Pad to shstrtab_offset
    while len(binary) < shstrtab_offset:
        binary.append(0)
    binary.extend(shstrtab)
    
    # Add symbol table and string table if present
    if has_symbols:
        while len(binary) < symtab_offset:
            binary.append(0)
        binary.extend(symtab_data)
        
        while len(binary) < strtab_offset:
            binary.append(0)
        binary.extend(strtab_data)
    
    # Pad to sht_offset
    while len(binary) < sht_offset:
        binary.append(0)
    
    # Section header table
    binary.extend(sh_null)
    binary.extend(sh_text)
    binary.extend(sh_shstrtab)
    
    # Add symbol table section headers if present
    if has_symbols:
        sh_symtab = struct.pack(
            "<IIIIIIIIII",
            17,             # sh_name: ".symtab" offset in shstrtab
            2,              # sh_type: SHT_SYMTAB
            0, 0,           # sh_flags, sh_addr
            symtab_offset,  # sh_offset
            symtab_size,    # sh_size
            4,              # sh_link: strtab section index
            1,              # sh_info: first non-local symbol
            4,              # sh_addralign
            16,             # sh_entsize: sizeof(Elf32_Sym)
        )
        binary.extend(sh_symtab)
        
        sh_strtab = struct.pack(
            "<IIIIIIIIII",
            25,             # sh_name: ".strtab" offset
            3,              # sh_type: SHT_STRTAB
            0, 0,           # sh_flags, sh_addr
            strtab_offset,  # sh_offset
            strtab_size,    # sh_size
            0, 0, 1, 0,     # sh_link, sh_info, sh_addralign, sh_entsize
        )
        binary.extend(sh_strtab)
    
    return bytes(binary)


def make_minimal_arm64_elf(entry: int = 0x400000) -> bytes:
    """Create a minimal 64-bit AArch64 ELF binary."""
    # AArch64 instructions: stp x29,x30,[sp,-16]!; mov x29,sp; ldp x29,x30,[sp],16; ret
    code = bytes([
        0xfd, 0x7b, 0xbf, 0xa9,  # stp x29, x30, [sp, #-16]!
        0xfd, 0x03, 0x00, 0x91,  # mov x29, sp
        0xfd, 0x7b, 0xc1, 0xa8,  # ldp x29, x30, [sp], #16
        0xc0, 0x03, 0x5f, 0xd6,  # ret
    ])
    
    shstrtab = b"\x00.text\x00.shstrtab\x00"
    shstrtab_offset = 0x100
    sht_offset = shstrtab_offset + len(shstrtab)
    sht_offset = (sht_offset + 7) & ~7  # Align to 8
    
    # 64-bit ELF header (64 bytes)
    elf_header = struct.pack(
        "<16sHHIQQQIHHHHHH",
        b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 8,  # e_ident (64-bit)
        2,              # e_type: ET_EXEC
        183,            # e_machine: EM_AARCH64
        1,              # e_version
        entry,          # e_entry
        0,              # e_phoff
        sht_offset,     # e_shoff
        0,              # e_flags
        64,             # e_ehsize
        0, 0,           # e_phentsize, e_phnum
        64,             # e_shentsize (64-bit section header)
        3,              # e_shnum
        2,              # e_shstrndx
    )
    
    # 64-bit section headers (64 bytes each)
    sh_null = struct.pack("<IIQQQQIIQQ", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    
    sh_text = struct.pack(
        "<IIQQQQIIQQ",
        1,              # sh_name
        1,              # sh_type: SHT_PROGBITS
        6,              # sh_flags
        entry,          # sh_addr
        64,             # sh_offset (after ELF header)
        len(code),      # sh_size
        0, 0,           # sh_link, sh_info
        4, 0,           # sh_addralign, sh_entsize
    )
    
    sh_shstrtab = struct.pack(
        "<IIQQQQIIQQ",
        7, 3, 0, 0, shstrtab_offset, len(shstrtab), 0, 0, 1, 0,
    )
    
    binary = bytearray()
    binary.extend(elf_header)
    binary.extend(code)
    while len(binary) < shstrtab_offset:
        binary.append(0)
    binary.extend(shstrtab)
    while len(binary) < sht_offset:
        binary.append(0)
    binary.extend(sh_null)
    binary.extend(sh_text)
    binary.extend(sh_shstrtab)
    
    return bytes(binary)


def make_minimal_riscv_elf(entry: int = 0x80000000) -> bytes:
    """Create a minimal 32-bit RISC-V ELF binary."""
    # RISC-V instructions: addi sp,sp,-16; sw ra,12(sp); lw ra,12(sp); addi sp,sp,16; ret
    code = bytes([
        0x01, 0x71,      # addi sp, sp, -16 (compressed)
        0x82, 0x80,      # ret (compressed)
    ])
    
    shstrtab = b"\x00.text\x00.shstrtab\x00"
    shstrtab_offset = 0x100
    sht_offset = (shstrtab_offset + len(shstrtab) + 3) & ~3
    
    elf_header = struct.pack(
        "<16sHHIIIIIHHHHHH",
        b"\x7fELF\x01\x01\x01\x00" + b"\x00" * 8,
        2,              # ET_EXEC
        243,            # EM_RISCV
        1, entry, 0, sht_offset, 0, 52, 0, 0, 40, 3, 2,
    )
    
    sh_null = struct.pack("<IIIIIIIIII", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    sh_text = struct.pack("<IIIIIIIIII", 1, 1, 6, entry, 52, len(code), 0, 0, 2, 0)
    sh_shstrtab = struct.pack("<IIIIIIIIII", 7, 3, 0, 0, shstrtab_offset, len(shstrtab), 0, 0, 1, 0)
    
    binary = bytearray()
    binary.extend(elf_header)
    binary.extend(code)
    while len(binary) < shstrtab_offset:
        binary.append(0)
    binary.extend(shstrtab)
    while len(binary) < sht_offset:
        binary.append(0)
    binary.extend(sh_null)
    binary.extend(sh_text)
    binary.extend(sh_shstrtab)
    
    return bytes(binary)


def make_raw_arm_binary() -> bytes:
    """Create raw ARM binary (no ELF header)."""
    return bytes([
        0x10, 0x40, 0x2d, 0xe9,  # push {r4, lr}
        0x00, 0x40, 0xa0, 0xe3,  # mov r4, #0
        0xfe, 0xff, 0xff, 0xea,  # b . (infinite loop)
        0x10, 0x40, 0xbd, 0xe8,  # pop {r4, pc}
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def arm32_elf() -> bytes:
    """Minimal ARM32 ELF binary."""
    return make_minimal_arm32_elf()


@pytest.fixture
def arm32_elf_with_symbols() -> bytes:
    """ARM32 ELF with function symbols."""
    return make_minimal_arm32_elf(
        entry=0x08000100,
        symbols=[
            ("main", 0x08000100, 12),
            ("helper_func", 0x08000200, 8),
        ],
    )


@pytest.fixture
def arm64_elf() -> bytes:
    """Minimal AArch64 ELF binary."""
    return make_minimal_arm64_elf()


@pytest.fixture
def riscv_elf() -> bytes:
    """Minimal RISC-V ELF binary."""
    return make_minimal_riscv_elf()


@pytest.fixture
def raw_arm_binary() -> bytes:
    """Raw ARM binary without ELF header."""
    return make_raw_arm_binary()


@pytest.fixture
def crash_log_lines() -> list[str]:
    """Sample crash log lines with PC addresses."""
    return [
        "[  123.456] Unable to handle kernel NULL pointer dereference",
        "[  123.457] PC is at 0x08000104",
        "[  123.458] LR is at 0x08000204",
        "[  123.459] pc : [<08000104>]    lr : [<08000204>]    psr: 600001d3",
        "[  123.460] Stack:",
        "[  123.461]  0x08000100 0x08000200 0x00000000 0x00000000",
        "[  123.462] Call trace:",
        "[  123.463]  [<08000104>] (main+0x4/0xc)",
        "[  123.464]  [<08000204>] (helper_func+0x4/0x8)",
    ]


@pytest.fixture
def x86_crash_log() -> list[str]:
    """Sample x86 crash log with RIP address."""
    return [
        "BUG: unable to handle kernel NULL pointer dereference at 0000000000000000",
        "RIP: 0010:main+0x12/0x40",
        "RIP: 0xffffffffc0123456",
        "Call Trace:",
        " ? main+0x12/0x40",
        " ? helper_func+0x5/0x20",
    ]
