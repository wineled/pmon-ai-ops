# backend/scripts/mock_tftp_push.py
"""
Mock TFTP push script — simulates an embedded board uploading a log file.

Usage:
    python -m scripts.mock_tftp_push [--dir <tftp_receive_dir>]

Creates a test log file in the TFTP receive directory with realistic
kernel Oops / metrics content so the pipeline can be tested end-to-end.
"""

from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

TEMPLATE_LOG = """\
[2026-04-15 00:00:00] INFO  Board boot complete, version=2.1.4
[2026-04-15 00:00:01] INFO  Ethernet link up, speed=1000Mbps
[2026-04-15 00:00:02] DEBUG Loading kernel module: pmon_core
[2026-04-15 00:00:03] INFO  Power voltage=3300 mv, current=450 ma, temp=42.1 c
[2026-04-15 00:00:04] DEBUG ADC calibration OK
[2026-04-15 00:00:05] WARNING Watchdog timer reset (timeout=30s)
[2026-04-15 00:00:06] INFO  Sensors: voltage=3298 mv, current=448 ma, temp=43.2 c
[2026-04-15 00:00:07] DEBUG Heartbeat sent to host
[2026-04-15 00:00:08] INFO  voltage=3301 mv, current=451 ma, temp=43.5 c
[2026-04-15 00:00:09] CRITICAL ------------[ cut here ]------------
[2026-04-15 00:00:09] CRITICAL kernel BUG at mm/slab.c:2847
[2026-04-15 00:00:09] CRITICAL Modules linked in: pmon_core gpio_pwm thermal
[2026-04-15 00:00:09] CRITICAL CPU: 0 PID: 1234 Comm: kworker/0:1
[2026-04-15 00:00:09] CRITICAL Hardware name: ARM-SoC rev B
[2026-04-15 00:00:09] CRITICAL Stack trace:
[2026-04-15 00:00:09] CRITICAL   [<c0012345>] kmalloc_order+0x18/0x2c
[2026-04-15 00:00:09] CRITICAL   [<c0056789>] alloc_pages_current+0xb0/0xd4
[2026-04-15 00:00:09] CRITICAL   [<c00abcde>] slab_alloc+0x1e0/0x448
[2026-04-15 00:00:09] CRITICAL   [<c00f1234>] kmem_cache_alloc+0x88/0xac
[2026-04-15 00:00:09] CRITICAL   [<c0123456>] device_probe+0x40/0xbc
[2026-04-15 00:00:09] CRITICAL   [<c0156789>] driver_probe_device+0x78/0xfc
[2026-04-15 00:00:09] CRITICAL   [<c0178901>] bus_for_each_dev+0x38/0x70
[2026-04-15 00:00:09] CRITICAL   [<c0189012>] bus_probe_devices+0x24/0x50
[2026-04-15 00:00:09] CRITICAL   [<c0201234>] watchdog_store+0x2c/0x78
[2026-04-15 00:00:09] CRITICAL r0: 0x00000000  r1: 0x00000001  r2: 0xc0012345
[2026-04-15 00:00:09] CRITICAL r3: 0x00000000  r4: 0xdeadbeef  r5: 0xc0100000
[2026-04-15 00:00:09] CRITICAL r6: 0x12345678  r7: 0x87654321  r8: 0x00000000
[2026-04-15 00:00:09] CRITICAL r9: 0x00000000  r10: 0x00000000  r11: 0x00000000
[2026-04-15 00:00:09] CRITICAL Flags: Nzcv | Control: 0x00000013
[2026-04-15 00:00:10] ERROR  Rebooting in 5 seconds...
[2026-04-15 00:00:15] INFO  Board rebooted
"""

TEMPLATE_METRICS_ONLY = """\
[2026-04-15 00:10:00] INFO  voltage=3299 mv, current=452 ma, temp=44.0 c
[2026-04-15 00:10:01] INFO  voltage=3300 mv, current=449 ma, temp=44.3 c
[2026-04-15 00:10:02] INFO  voltage=3298 mv, current=451 ma, temp=44.5 c
"""


def push_mock_log(tftp_dir: Path, board_id: str, with_error: bool = False) -> Path:
    """Write a mock log file into tftp_dir and return the path."""
    tftp_dir.mkdir(parents=True, exist_ok=True)
    content = TEMPLATE_LOG if with_error else TEMPLATE_METRICS_ONLY

    # Inject some random voltage/current variance for realistic metrics
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if "voltage=" in line.lower():
            base_v = random.uniform(3200, 3400)
            lines[i] = lines[i].replace("3300", f"{base_v:.0f}")
        if "current=" in line.lower():
            base_c = random.uniform(400, 500)
            lines[i] = lines[i].replace("450", f"{base_c:.0f}")

    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{board_id}_{ts}.log"
    path = tftp_dir / filename
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[Mock] Created: {path} ({path.stat().st_size} bytes)")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push a mock log file to the TFTP receive directory")
    parser.add_argument("--dir", type=Path, default=Path("./tftp_receive"), help="TFTP receive directory")
    parser.add_argument("--board", default="board01", help="Board ID")
    parser.add_argument("--error", action="store_true", help="Include kernel BUG/Oops")
    args = parser.parse_args()

    push_mock_log(args.dir, args.board, with_error=args.error)
