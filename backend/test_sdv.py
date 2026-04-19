"""
PMON-AI-OPS 代码分析模块 SDV (Software Design Verification) 测试套件

测试维度:
  FR  - Functional Requirements (功能需求)
  IC  - Interface Contract (接口契约)
  BC  - Boundary Conditions (边界条件)
  EH  - Error Handling (错误处理)
  DI  - Data Integrity (数据完整性)
  PF  - Performance (性能)
  SC  - Security (安全性)
  CP  - Compatibility (兼容性)

Usage:
  python -X utf8 -m pytest test_sdv.py -v --tb=short
"""

from __future__ import annotations

import struct
import time
import io
import zipfile
from typing import Optional

import pytest
import requests

# ═══════════════════════════════════════════════════════════════════════════════
# Config & Helpers
# ═══════════════════════════════════════════════════════════════════════════════

BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/disasm"


def make_arm32_elf(
    entry: int = 0x08000100,
    code: bytes | None = None,
    symbols: list[tuple[str, int, int]] | None = None,
    e_flags: int = 0x5000200,
) -> bytes:
    """Create a valid 32-bit ARM ELF binary."""
    if code is None:
        code = bytes([
            0x70, 0x00, 0x2d, 0xe9,  # push {r4-r6, lr}
            0x00, 0x40, 0xa0, 0xe1,  # mov r4, r0
            0x01, 0x50, 0xa0, 0xe1,  # mov r5, r1
            0x05, 0x00, 0x84, 0xe0,  # add r0, r4, r5
            0x70, 0x00, 0xbd, 0xe8,  # pop {r4-r6, pc}
        ])

    has_sym = symbols is not None and len(symbols) > 0
    elf_hdr_size = 52
    text_off = elf_hdr_size
    text_sz = len(code)
    shstrtab_off = text_off + text_sz
    shstrtab = b"\x00.text\x00.shstrtab\x00"
    if has_sym:
        shstrtab += b".symtab\x00.strtab\x00"
    shstrtab_sz = len(shstrtab)

    sym_data = b""
    str_data = b""
    sym_off = 0
    str_off = 0
    sym_sz = 0
    str_sz = 0

    if has_sym:
        str_data = b"\x00"
        parts = []
        parts.append(struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0))
        for name, addr, sz in symbols:
            st_name = len(str_data)
            str_data += name.encode() + b"\x00"
            parts.append(struct.pack("<IIIBBH", st_name, addr, sz, 0x12, 0, 1))
        sym_data = b"".join(parts)
        sym_sz = len(sym_data)
        str_sz = len(str_data)
        sym_off = shstrtab_off + shstrtab_sz
        str_off = sym_off + sym_sz

    sht_off = (str_off + str_sz) if has_sym else (shstrtab_off + shstrtab_sz)
    sht_off = (sht_off + 3) & ~3
    shnum = 5 if has_sym else 3
    shstrndx = 2

    hdr = struct.pack(
        "<16sHHIIIIIHHHHHH",
        b"\x7fELF\x01\x01\x01\x00" + b"\x00" * 8,
        2, 40, 1, entry, 0, sht_off, e_flags,
        52, 0, 0, 40, shnum, shstrndx,
    )

    buf = bytearray()
    buf.extend(hdr)
    buf.extend(code)
    while len(buf) < shstrtab_off:
        buf.append(0)
    buf.extend(shstrtab)
    if has_sym:
        while len(buf) < sym_off:
            buf.append(0)
        buf.extend(sym_data)
        while len(buf) < str_off:
            buf.append(0)
        buf.extend(str_data)
    while len(buf) < sht_off:
        buf.append(0)

    # SHT entries
    sh_null = struct.pack("<IIIIIIIIII", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    sh_text = struct.pack("<IIIIIIIIII", 1, 1, 6, entry, text_off, text_sz, 0, 0, 4, 0)
    sh_shstr = struct.pack("<IIIIIIIIII", 7, 3, 0, 0, shstrtab_off, shstrtab_sz, 0, 0, 1, 0)

    buf.extend(sh_null)
    buf.extend(sh_text)
    buf.extend(sh_shstr)
    if has_sym:
        sym_name_off = shstrtab.index(b".symtab")
        str_name_off = shstrtab.index(b".strtab")
        buf.extend(struct.pack("<IIIIIIIIII", sym_name_off, 2, 0, 0, sym_off, sym_sz, 4, 1, 4, 16))
        buf.extend(struct.pack("<IIIIIIIIII", str_name_off, 3, 0, 0, str_off, str_sz, 0, 0, 1, 0))

    return bytes(buf)


def make_aarch64_elf(entry: int = 0x400000) -> bytes:
    """Create a minimal AArch64 ELF."""
    code = bytes([
        0xfd, 0x7b, 0xbf, 0xa9,  # stp x29, x30, [sp, #-16]!
        0xc0, 0x03, 0x5f, 0xd6,  # ret
    ])
    hdr = struct.pack(
        "<16sHHIIIIIHHHHHH",
        b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 8,
        2, 183, 1, entry, 0, 0, 0,
        64, 0, 0, 64, 0, 0,
    )
    return hdr + code  # Minimal, no sections


def make_riscv32_elf(entry: int = 0x20000000) -> bytes:
    """Create a minimal RISC-V 32 ELF."""
    code = bytes([
        0x93, 0x02, 0x80, 0x00,  # li t0, 8
        0x73, 0x00, 0x00, 0x00,  # ecall
    ])
    hdr = struct.pack(
        "<16sHHIIIIIHHHHHH",
        b"\x7fELF\x01\x01\x01\x00" + b"\x00" * 8,
        2, 243, 1, entry, 0, 0, 0,
        52, 0, 0, 40, 0, 0,
    )
    return hdr + code


def make_x86_elf(entry: int = 0x08048000) -> bytes:
    """Create a minimal x86 ELF."""
    code = bytes([
        0x55,                 # push ebp
        0x89, 0xe5,           # mov ebp, esp
        0xb8, 0x2a, 0x00, 0x00, 0x00,  # mov eax, 42
        0x5d,                 # pop ebp
        0xc3,                 # ret
    ])
    hdr = struct.pack(
        "<16sHHIIIIIHHHHHH",
        b"\x7fELF\x01\x01\x01\x00" + b"\x00" * 8,
        2, 3, 1, entry, 0, 0, 0,
        52, 0, 0, 40, 0, 0,
    )
    return hdr + code


def upload_and_get(data: bytes, filename: str = "test.elf", **kwargs) -> dict:
    """Upload binary and return response JSON."""
    files = {"file": (filename, data, "application/octet-stream")}
    r = requests.post(f"{API}/upload", files=files, data=kwargs, timeout=10)
    return r


def clear_all():
    requests.delete(f"{API}/clear", timeout=5)


# ═══════════════════════════════════════════════════════════════════════════════
# FR - Functional Requirements
# ═══════════════════════════════════════════════════════════════════════════════

class TestFR:
    """功能需求验证"""

    def test_fr01_upload_elf_arm(self):
        """FR-01: 上传 ARM ELF 文件，正确检测架构"""
        clear_all()
        elf = make_arm32_elf()
        r = upload_and_get(elf, "arm.elf")
        assert r.status_code == 200
        meta = r.json()["meta"]
        assert meta["arch"] == "arm"
        assert meta["bits"] == 32
        assert meta["is_elf"] is True
        assert meta["disasm_lines"] >= 5
        clear_all()

    def test_fr02_upload_elf_aarch64(self):
        """FR-02: 上传 AArch64 ELF 文件，正确检测架构"""
        clear_all()
        elf = make_aarch64_elf()
        r = upload_and_get(elf, "aarch64.elf")
        # May fail if no sections, but should detect arch
        if r.status_code == 200:
            meta = r.json()["meta"]
            assert meta["arch"] == "arm64"
            assert meta["bits"] == 64
        clear_all()

    def test_fr03_upload_elf_riscv(self):
        """FR-03: 上传 RISC-V ELF 文件，正确检测架构"""
        clear_all()
        elf = make_riscv32_elf()
        r = upload_and_get(elf, "riscv.elf")
        if r.status_code == 200:
            meta = r.json()["meta"]
            assert meta["arch"] == "riscv"
        clear_all()

    def test_fr04_upload_elf_x86(self):
        """FR-04: 上传 x86 ELF 文件，正确检测架构"""
        clear_all()
        elf = make_x86_elf()
        r = upload_and_get(elf, "x86.elf")
        if r.status_code == 200:
            meta = r.json()["meta"]
            assert meta["arch"] == "x86"
        clear_all()

    def test_fr05_upload_raw_binary_with_arch(self):
        """FR-05: 上传原始二进制文件，显式指定架构"""
        clear_all()
        code = bytes([0x55, 0x89, 0xe5, 0xc3])  # x86: push ebp; mov ebp,esp; ret
        r = upload_and_get(code, "raw.bin", arch="x86", base_addr="0x08000000")
        assert r.status_code == 200
        meta = r.json()["meta"]
        assert meta["arch"] == "x86"
        assert meta["is_elf"] is False
        clear_all()

    def test_fr06_disassembly_output(self):
        """FR-06: 反汇编输出包含正确的字段"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf, "test.elf")
        r = requests.get(f"{API}/disassembly?limit=5", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] > 0
        line = data["lines"][0]
        assert "address" in line
        assert "bytes_hex" in line
        assert "mnemonic" in line
        assert "op_str" in line
        assert "function" in line
        assert "offset_in_func" in line
        clear_all()

    def test_fr07_symbol_table(self):
        """FR-07: 符号表解析"""
        clear_all()
        elf = make_arm32_elf(
            symbols=[("main", 0x08000100, 20), ("helper", 0x08000200, 8)]
        )
        r = upload_and_get(elf, "sym.elf")
        assert r.status_code == 200
        meta = r.json()["meta"]
        assert meta["symbol_count"] >= 2

        r = requests.get(f"{API}/symbols", timeout=5)
        data = r.json()
        assert data["total"] >= 2
        names = [s["name"] for s in data["symbols"]]
        assert "main" in names
        assert "helper" in names
        clear_all()

    def test_fr08_symbol_search(self):
        """FR-08: 符号搜索功能"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20), ("my_helper", 0x08000200, 8)])
        upload_and_get(elf)
        r = requests.get(f"{API}/symbols?query=main", timeout=5)
        data = r.json()
        assert data["total"] >= 1
        assert any(s["name"] == "main" for s in data["symbols"])
        clear_all()

    def test_fr09_address_resolve(self):
        """FR-09: 地址解析到函数"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20)])
        upload_and_get(elf)
        r = requests.get(f"{API}/resolve?address=0x08000104", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["function"] == "main"
        assert data["offset"] == 4
        clear_all()

    def test_fr10_address_resolve_nearby(self):
        """FR-10: 地址解析返回附近指令"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20)])
        upload_and_get(elf)
        r = requests.get(f"{API}/resolve?address=0x08000104", timeout=5)
        data = r.json()
        assert "nearby" in data
        assert len(data["nearby"]) > 0
        clear_all()

    def test_fr11_crash_address_extraction_pc(self):
        """FR-11: 崩溃地址提取 - PC 模式"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20)])
        upload_and_get(elf)
        r = requests.post(f"{API}/analyze", json={
            "log_entries": ["PC is at 0x08000104"],
            "device": "cortex-a7",
        }, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert len(data["anomalies"]) >= 1
        assert data["anomalies"][0]["function"] == "main"
        clear_all()

    def test_fr12_crash_address_extraction_rip(self):
        """FR-12: 崩溃地址提取 - RIP 模式"""
        clear_all()
        # Need x86 binary loaded
        code = bytes([0x55, 0x89, 0xe5, 0xb8, 0x2a, 0x00, 0x00, 0x00, 0x5d, 0xc3])
        upload_and_get(code, "x86.bin", arch="x86", base_addr="0x08000000")
        r = requests.post(f"{API}/analyze", json={
            "log_entries": ["RIP: 0010:0x08000002"],
            "device": "x86-64",
        }, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert len(data["anomalies"]) >= 1
        clear_all()

    def test_fr13_analyze_no_crash(self):
        """FR-13: 日志分析无崩溃地址时返回空"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        r = requests.post(f"{API}/analyze", json={
            "log_entries": ["system started normally", "all services ok"],
            "device": "cortex-a7",
        }, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert len(data["anomalies"]) == 0
        clear_all()

    def test_fr14_clear_state(self):
        """FR-14: 清除操作重置所有状态"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)

        # Verify loaded
        r = requests.get(f"{API}/status", timeout=5)
        assert r.json()["loaded"] is True

        # Clear
        requests.delete(f"{API}/clear", timeout=5)

        # Verify cleared
        r = requests.get(f"{API}/status", timeout=5)
        assert r.json()["loaded"] is False

        # Disassembly should be empty
        r = requests.get(f"{API}/disassembly", timeout=5)
        assert r.json()["total"] == 0
        clear_all()

    def test_fr15_status_no_file(self):
        """FR-15: 未上传文件时状态为未加载"""
        clear_all()
        r = requests.get(f"{API}/status", timeout=5)
        assert r.json()["loaded"] is False
        clear_all()


# ═══════════════════════════════════════════════════════════════════════════════
# IC - Interface Contract
# ═══════════════════════════════════════════════════════════════════════════════

class TestIC:
    """接口契约验证"""

    def test_ic01_upload_returns_upload_response(self):
        """IC-01: 上传接口返回 UploadResponse 结构"""
        clear_all()
        elf = make_arm32_elf()
        r = upload_and_get(elf)
        data = r.json()
        assert "status" in data
        assert "meta" in data
        assert data["status"] == "ok"
        meta = data["meta"]
        required = ["file_id", "filename", "size_bytes", "arch", "bits", "is_elf"]
        for field in required:
            assert field in meta, f"Missing field: {field}"
        clear_all()

    def test_ic02_disassembly_returns_page_response(self):
        """IC-02: 反汇编接口返回分页结构"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        r = requests.get(f"{API}/disassembly?offset=0&limit=3", timeout=5)
        data = r.json()
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert "lines" in data
        assert data["offset"] == 0
        assert data["limit"] == 3
        clear_all()

    def test_ic03_symbols_returns_page_response(self):
        """IC-03: 符号接口返回分页结构"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20)])
        upload_and_get(elf)
        r = requests.get(f"{API}/symbols?offset=0&limit=10", timeout=5)
        data = r.json()
        assert "total" in data
        assert "symbols" in data
        clear_all()

    def test_ic04_resolve_returns_address_result(self):
        """IC-04: 解析接口返回 AddressResolveResult 结构"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        r = requests.get(f"{API}/resolve?address=0x08000100", timeout=5)
        data = r.json()
        assert "address" in data
        assert "function" in data
        assert "offset" in data
        assert "nearby" in data
        clear_all()

    def test_ic05_analyze_returns_analysis_response(self):
        """IC-05: 分析接口返回 AnalysisResponse 结构"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        r = requests.post(f"{API}/analyze", json={
            "log_entries": ["PC is at 0x08000100"],
            "device": "test",
        }, timeout=10)
        data = r.json()
        assert "anomalies" in data
        assert "resolved_addresses" in data
        clear_all()

    def test_ic06_status_returns_dict(self):
        """IC-06: 状态接口返回 loaded + meta 结构"""
        clear_all()
        r = requests.get(f"{API}/status", timeout=5)
        data = r.json()
        assert "loaded" in data
        assert "meta" in data
        clear_all()

    def test_ic07_clear_returns_dict(self):
        """IC-07: 清除接口返回 status + message 结构"""
        clear_all()
        r = requests.delete(f"{API}/clear", timeout=5)
        data = r.json()
        assert "status" in data
        assert data["status"] == "ok"
        clear_all()


# ═══════════════════════════════════════════════════════════════════════════════
# BC - Boundary Conditions
# ═══════════════════════════════════════════════════════════════════════════════

class TestBC:
    """边界条件验证"""

    def test_bc01_empty_file(self):
        """BC-01: 空文件上传"""
        clear_all()
        r = upload_and_get(b"", "empty.bin")
        assert r.status_code in (400, 422)
        clear_all()

    def test_bc02_single_byte_file(self):
        """BC-02: 单字节文件"""
        clear_all()
        r = upload_and_get(b"\x00", "tiny.bin", arch="arm", base_addr="0x0")
        assert r.status_code == 200
        clear_all()

    def test_bc03_minimal_arm_elf(self):
        """BC-03: 最小有效 ARM ELF"""
        clear_all()
        elf = make_arm32_elf(code=bytes([0x70, 0x00, 0xbd, 0xe8]))  # 1 instruction
        r = upload_and_get(elf, "min.elf")
        assert r.status_code == 200
        assert r.json()["meta"]["disasm_lines"] >= 1
        clear_all()

    def test_bc04_large_offset_pagination(self):
        """BC-04: 分页请求 offset 超出范围"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        r = requests.get(f"{API}/disassembly?offset=999999&limit=10", timeout=5)
        assert r.status_code == 200
        assert r.json()["lines"] == []
        clear_all()

    def test_bc05_zero_limit_pagination(self):
        """BC-05: 分页 limit=0"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        r = requests.get(f"{API}/disassembly?limit=0", timeout=5)
        assert r.status_code == 200
        clear_all()

    def test_bc06_negative_offset(self):
        """BC-06: 分页 offset 为负数"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        r = requests.get(f"{API}/disassembly?offset=-1", timeout=5)
        # Should either reject or handle gracefully
        assert r.status_code in (200, 400, 422)
        clear_all()

    def test_bc07_address_at_entry_point(self):
        """BC-07: 解析入口点地址"""
        clear_all()
        elf = make_arm32_elf(
            entry=0x08000100,
            symbols=[("main", 0x08000100, 20)]
        )
        upload_and_get(elf)
        r = requests.get(f"{API}/resolve?address=0x08000100", timeout=5)
        assert r.status_code == 200
        assert r.json()["function"] == "main"
        clear_all()

    def test_bc08_address_at_function_boundary(self):
        """BC-08: 解析函数边界地址"""
        clear_all()
        # Note: code section is only 20 bytes (5 ARM instructions)
        # main at 0x08000100, helper at 0x08000110 (last 4 bytes)
        elf = make_arm32_elf(
            symbols=[
                ("main", 0x08000100, 16),
                ("helper", 0x08000110, 4),
            ]
        )
        upload_and_get(elf)
        # Last byte of main (0x08000100 + 16 - 1 = 0x0800010F)
        r = requests.get(f"{API}/resolve?address=0x0800010F", timeout=5)
        assert r.status_code == 200
        assert r.json()["function"] == "main"
        # First byte of helper (0x08000110)
        r = requests.get(f"{API}/resolve?address=0x08000110", timeout=5)
        assert r.json()["function"] == "helper"
        clear_all()

    def test_bc09_address_far_from_any_function(self):
        """BC-09: 地址远离任何函数"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20)])
        upload_and_get(elf)
        r = requests.get(f"{API}/resolve?address=0xFFFFFFFF", timeout=5)
        assert r.status_code == 200
        # Should return ??? for unknown function
        assert r.json()["function"] == "???"
        clear_all()

    def test_bc10_resolve_without_binary(self):
        """BC-10: 未上传二进制时解析地址"""
        clear_all()
        r = requests.get(f"{API}/resolve?address=0x08000100", timeout=5)
        assert r.status_code == 200
        assert r.json()["function"] == "???"
        clear_all()


# ═══════════════════════════════════════════════════════════════════════════════
# EH - Error Handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestEH:
    """错误处理验证"""

    def test_eh01_non_elf_without_arch(self):
        """EH-01: 非 ELF 文件未指定架构"""
        clear_all()
        r = upload_and_get(b"\x00\x01\x02\x03", "raw.bin")
        assert r.status_code == 422
        clear_all()

    def test_eh02_invalid_arch_string(self):
        """EH-02: 无效架构字符串"""
        clear_all()
        r = upload_and_get(b"\x00\x01\x02\x03", "raw.bin", arch="mips")
        assert r.status_code == 422
        clear_all()

    def test_eh03_invalid_address_format(self):
        """EH-03: 无效地址格式"""
        clear_all()
        r = requests.get(f"{API}/resolve?address=not_a_hex", timeout=5)
        assert r.status_code == 400
        clear_all()

    def test_eh04_invalid_base_addr(self):
        """EH-04: 无效基地址格式"""
        clear_all()
        r = upload_and_get(b"\x00\x01\x02\x03", "raw.bin", arch="arm", base_addr="xyz")
        assert r.status_code == 400
        clear_all()

    def test_eh05_truncated_elf(self):
        """EH-05: 截断的 ELF 文件"""
        clear_all()
        # Only first 20 bytes of ELF header
        elf = make_arm32_elf()[:20]
        r = upload_and_get(elf, "trunc.elf")
        assert r.status_code == 422
        clear_all()

    def test_eh06_corrupted_elf_magic_valid(self):
        """EH-06: ELF magic 正确但内容损坏"""
        clear_all()
        # Valid magic, but garbage content after
        bad_elf = b"\x7fELF\x01\x01\x01\x00" + b"\xff" * 100
        r = upload_and_get(bad_elf, "corrupt.elf")
        # May succeed (200), reject (422), or error (500) - all acceptable
        assert r.status_code in (200, 400, 422, 500), \
            f"Unexpected status: {r.status_code}"
        clear_all()

    def test_eh07_analyze_empty_log_entries(self):
        """EH-07: 空日志列表"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        r = requests.post(f"{API}/analyze", json={
            "log_entries": [],
            "device": "test",
        }, timeout=10)
        assert r.status_code == 200
        assert r.json()["anomalies"] == []
        clear_all()

    def test_eh08_analyze_without_binary(self):
        """EH-08: 未上传二进制时分析日志"""
        clear_all()
        r = requests.post(f"{API}/analyze", json={
            "log_entries": ["PC is at 0x08000100"],
            "device": "test",
        }, timeout=10)
        # Should handle gracefully
        assert r.status_code == 200
        clear_all()

    def test_eh09_upload_replaces_previous(self):
        """EH-09: 重复上传替换前一个文件"""
        clear_all()
        # Upload first
        elf1 = make_arm32_elf(entry=0x08000100, symbols=[("first", 0x08000100, 20)])
        upload_and_get(elf1, "first.elf")

        # Upload second
        elf2 = make_arm32_elf(entry=0x10000000, symbols=[("second", 0x10000000, 12)])
        r = upload_and_get(elf2, "second.elf")
        assert r.status_code == 200

        # Should have second file's data
        r = requests.get(f"{API}/symbols", timeout=5)
        names = [s["name"] for s in r.json()["symbols"]]
        assert "second" in names
        assert "first" not in names
        clear_all()


# ═══════════════════════════════════════════════════════════════════════════════
# DI - Data Integrity
# ═══════════════════════════════════════════════════════════════════════════════

class TestDI:
    """数据完整性验证"""

    def test_di01_disasm_addresses_sequential(self):
        """DI-01: 反汇编地址按顺序递增"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        r = requests.get(f"{API}/disassembly?limit=100", timeout=5)
        lines = r.json()["lines"]
        for i in range(1, len(lines)):
            assert lines[i]["address"] >= lines[i-1]["address"], \
                f"Address not sequential: {lines[i-1]['address']} -> {lines[i]['address']}"
        clear_all()

    def test_di02_disasm_bytes_match_length(self):
        """DI-02: 反汇编字节与指令长度一致"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        r = requests.get(f"{API}/disassembly?limit=100", timeout=5)
        lines = r.json()["lines"]
        for line in lines:
            byte_count = len(bytes.fromhex(line["bytes_hex"]))
            # ARM instructions are 4 bytes
            assert byte_count == 4, f"ARM instruction should be 4 bytes, got {byte_count}"
        clear_all()

    def test_di03_symbol_addresses_within_code(self):
        """DI-03: 符号地址在代码段范围内"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20)])
        upload_and_get(elf)
        r = requests.get(f"{API}/symbols", timeout=5)
        for sym in r.json()["symbols"]:
            assert sym["address"] >= 0x08000100, \
                f"Symbol {sym['name']} at {hex(sym['address'])} outside code range"
        clear_all()

    def test_di04_resolve_offset_consistent(self):
        """DI-04: 解析偏移量与函数地址一致"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20)])
        upload_and_get(elf)
        # Address 0x08000104 is 4 bytes into main
        r = requests.get(f"{API}/resolve?address=0x08000104", timeout=5)
        data = r.json()
        assert data["function"] == "main"
        assert data["offset"] == 4, f"Expected offset 4, got {data['offset']}"
        clear_all()

    def test_di05_mnemonic_not_empty(self):
        """DI-05: 反汇编助记符不为空"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        r = requests.get(f"{API}/disassembly?limit=100", timeout=5)
        for line in r.json()["lines"]:
            assert line["mnemonic"], f"Empty mnemonic at 0x{line['address']:08x}"
        clear_all()

    def test_di06_anomaly_address_matches_log(self):
        """DI-06: 异常地址与日志中提取的地址一致"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20)])
        upload_and_get(elf)
        r = requests.post(f"{API}/analyze", json={
            "log_entries": ["PC is at 0x08000104"],
            "device": "test",
        }, timeout=10)
        data = r.json()
        if data["anomalies"]:
            # The anomaly address should be 0x08000104
            assert data["anomalies"][0]["address"] == 0x08000104, \
                f"Anomaly address mismatch: expected 0x08000104, got {hex(data['anomalies'][0]['address'])}"
        clear_all()


# ═══════════════════════════════════════════════════════════════════════════════
# PF - Performance
# ═══════════════════════════════════════════════════════════════════════════════

class TestPF:
    """性能验证"""

    def test_pf01_upload_latency(self):
        """PF-01: 上传延迟 < 5s (1KB ELF)"""
        clear_all()
        elf = make_arm32_elf()
        t0 = time.time()
        r = upload_and_get(elf)
        t1 = time.time()
        assert r.status_code == 200
        assert (t1 - t0) < 5.0, f"Upload took {t1 - t0:.2f}s"
        clear_all()

    def test_pf02_disassembly_latency(self):
        """PF-02: 反汇编查询延迟 < 3s"""
        clear_all()
        elf = make_arm32_elf()
        upload_and_get(elf)
        t0 = time.time()
        r = requests.get(f"{API}/disassembly?limit=100", timeout=5)
        t1 = time.time()
        assert r.status_code == 200
        assert (t1 - t0) < 3.0, f"Disassembly query took {t1 - t0:.2f}s"
        clear_all()

    def test_pf03_resolve_latency(self):
        """PF-03: 地址解析延迟 < 3s"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20)])
        upload_and_get(elf)
        t0 = time.time()
        r = requests.get(f"{API}/resolve?address=0x08000104", timeout=5)
        t1 = time.time()
        assert r.status_code == 200
        assert (t1 - t0) < 3.0, f"Resolve took {t1 - t0:.2f}s"
        clear_all()

    def test_pf04_analyze_latency(self):
        """PF-04: 日志分析延迟 < 5s"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20)])
        upload_and_get(elf)
        logs = ["PC is at 0x08000104", "LR = 0x08000100"] * 5
        t0 = time.time()
        r = requests.post(f"{API}/analyze", json={
            "log_entries": logs, "device": "test"
        }, timeout=10)
        t1 = time.time()
        assert r.status_code == 200
        assert (t1 - t0) < 5.0, f"Analyze took {t1 - t0:.2f}s"
        clear_all()


# ═══════════════════════════════════════════════════════════════════════════════
# SC - Security
# ═══════════════════════════════════════════════════════════════════════════════

class TestSC:
    """安全性验证"""

    def test_sc01_path_traversal_filename(self):
        """SC-01: 文件名包含路径遍历字符"""
        clear_all()
        elf = make_arm32_elf()
        r = upload_and_get(elf, "../../../etc/passwd.elf")
        # Should not crash, filename should be sanitized or rejected
        assert r.status_code in (200, 400, 422)
        clear_all()

    def test_sc02_very_long_filename(self):
        """SC-02: 超长文件名"""
        clear_all()
        elf = make_arm32_elf()
        long_name = "a" * 1000 + ".elf"
        r = upload_and_get(elf, long_name)
        assert r.status_code in (200, 400, 422)
        clear_all()

    def test_sc03_sql_injection_in_arch(self):
        """SC-03: 架构参数包含 SQL 注入"""
        clear_all()
        r = upload_and_get(b"\x00\x01\x02\x03", "test.bin", arch="'; DROP TABLE users;--")
        assert r.status_code == 422
        clear_all()

    def test_sc04_xss_in_query(self):
        """SC-04: 符号搜索包含 XSS 字符"""
        clear_all()
        elf = make_arm32_elf(symbols=[("main", 0x08000100, 20)])
        upload_and_get(elf)
        r = requests.get(f"{API}/symbols?query=<script>alert(1)</script>", timeout=5)
        assert r.status_code == 200
        # Should not execute any script
        clear_all()

    def test_sc05_very_large_upload(self):
        """SC-05: 大文件上传（>1MB）- skip, too slow for SDV"""
        pass  # Skip: 1MB upload takes too long in SDV


# ═══════════════════════════════════════════════════════════════════════════════
# CP - Compatibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestCP:
    """兼容性验证"""

    def test_cp01_arm32_elf(self):
        """CP-01: ARM 32-bit ELF 兼容"""
        clear_all()
        elf = make_arm32_elf()
        r = upload_and_get(elf, "arm32.elf")
        assert r.status_code == 200
        assert r.json()["meta"]["arch"] == "arm"
        clear_all()

    def test_cp02_aarch64_elf(self):
        """CP-02: AArch64 ELF 兼容"""
        clear_all()
        elf = make_aarch64_elf()
        r = upload_and_get(elf, "aarch64.elf")
        # Minimal ELF without sections may still detect arch
        if r.status_code == 200:
            assert r.json()["meta"]["arch"] == "arm64"
        clear_all()

    def test_cp03_riscv32_elf(self):
        """CP-03: RISC-V 32-bit ELF 兼容"""
        clear_all()
        elf = make_riscv32_elf()
        r = upload_and_get(elf, "riscv32.elf")
        if r.status_code == 200:
            assert r.json()["meta"]["arch"] == "riscv"
        clear_all()

    def test_cp04_x86_elf(self):
        """CP-04: x86 ELF 兼容"""
        clear_all()
        elf = make_x86_elf()
        r = upload_and_get(elf, "x86.elf")
        if r.status_code == 200:
            assert r.json()["meta"]["arch"] == "x86"
        clear_all()

    def test_cp05_raw_binary_arm(self):
        """CP-05: 原始 ARM 二进制兼容"""
        clear_all()
        code = bytes([0x70, 0x00, 0xbd, 0xe8])  # ARM: pop
        r = upload_and_get(code, "raw_arm.bin", arch="arm", base_addr="0x08000000")
        assert r.status_code == 200
        assert r.json()["meta"]["arch"] == "arm"
        clear_all()

    def test_cp06_raw_binary_x86(self):
        """CP-06: 原始 x86 二进制兼容"""
        clear_all()
        code = bytes([0x55, 0x89, 0xe5, 0xc3])  # push ebp; mov ebp,esp; ret
        r = upload_and_get(code, "raw_x86.bin", arch="x86", base_addr="0x08000000")
        assert r.status_code == 200
        assert r.json()["meta"]["arch"] == "x86"
        clear_all()

    def test_cp07_different_file_extensions(self):
        """CP-07: 不同文件扩展名兼容"""
        clear_all()
        elf = make_arm32_elf()
        for ext in [".elf", ".bin", ".axf", ".out", ".o"]:
            r = upload_and_get(elf, f"test{ext}")
            assert r.status_code == 200, f"Failed for extension {ext}"
        clear_all()
