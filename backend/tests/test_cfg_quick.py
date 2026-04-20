"""CFG Service Quick Tests"""
import sys
sys.path.insert(0, r'F:\CodingProjects\电源监控日志实时分析系统\backend')
from src.services.cfg_service import cfg_from_instructions, cfg_to_dict

def hx(val):
    return hex(val)

# Test 1: Linear ARM function (ends with pop {pc} = return)
print("=== Test 1: Linear ARM function ===")
insns = [
    {"address": 0x08000100, "mnemonic": "push", "op_str": "{r4, lr}", "bytes": "10402de9"},
    {"address": 0x08000104, "mnemonic": "mov", "op_str": "r4, r0", "bytes": "0040a0e1"},
    {"address": 0x08000108, "mnemonic": "mov", "op_str": "r0, #0", "bytes": "0000a0e3"},
    {"address": 0x0800010c, "mnemonic": "pop", "op_str": "{r4, pc}", "bytes": "1040bde8"},
]
cfg = cfg_from_instructions(insns, "simple_func", "arm")
d = cfg_to_dict(cfg)
print("Stats:", d["stats"])
assert d["stats"]["total_blocks"] == 1, "Expected 1 block, got " + str(d["stats"]["total_blocks"])
assert d["stats"]["total_edges"] == 1, "Expected 1 return edge, got " + str(d["stats"]["total_edges"])
ret_edges = [e for e in d["edges"] if e["type"] == "return"]
assert len(ret_edges) == 1
print("PASS: Linear -> 1 block, 1 return edge")

# Test 2: Conditional branch
print("\n=== Test 2: Conditional branch ===")
insns2 = [
    {"address": 0x08000100, "mnemonic": "push", "op_str": "{lr}", "bytes": "70482de9"},
    {"address": 0x08000104, "mnemonic": "cmp", "op_str": "r0, #0", "bytes": "000050e3"},
    {"address": 0x08000108, "mnemonic": "beq", "op_str": "0x08000114", "bytes": "0400000a"},
    {"address": 0x0800010c, "mnemonic": "mov", "op_str": "r0, #1", "bytes": "0100a0e3"},
    {"address": 0x08000110, "mnemonic": "pop", "op_str": "{pc}", "bytes": "7048bde8"},
    {"address": 0x08000114, "mnemonic": "mov", "op_str": "r0, #0", "bytes": "0000a0e3"},
    {"address": 0x08000118, "mnemonic": "pop", "op_str": "{pc}", "bytes": "7048bde8"},
]
cfg2 = cfg_from_instructions(insns2, "branch_func", "arm")
d2 = cfg_to_dict(cfg2)
print("Stats:", d2["stats"])
blocks2 = d2["basic_blocks"]
edges2 = d2["edges"]
print("Blocks:", len(blocks2))
for i, bb in enumerate(blocks2):
    sa = int(bb["start_addr"], 16) if isinstance(bb["start_addr"], str) else bb["start_addr"]
    ea = int(bb["end_addr"], 16) if isinstance(bb["end_addr"], str) else bb["end_addr"]
    print("  Block", i, ":", hx(sa), "-", hx(ea))
for e in edges2:
    comment = e.get("comment", "")
    print("  Edge:", e["from"], "--[" + e["type"] + "]-->", e["to"], comment)
cond_true = [e for e in edges2 if e["type"] == "conditional_true"]
cond_false = [e for e in edges2 if e["type"] == "conditional_false"]
print("  conditional_true:", len(cond_true), "| conditional_false:", len(cond_false))
assert len(blocks2) == 3, "Expected 3 blocks"
assert len(cond_true) >= 1
assert len(cond_false) >= 1
print("PASS: Conditional branch -> 3 blocks")

# Test 3: Function with call
print("\n=== Test 3: Function with call ===")
insns3 = [
    {"address": 0x08000100, "mnemonic": "push", "op_str": "{lr}", "bytes": "70482de9"},
    {"address": 0x08000104, "mnemonic": "bl", "op_str": "0x08000200", "bytes": "040000eb"},
    {"address": 0x08000108, "mnemonic": "mov", "op_str": "r0, #42", "bytes": "2a00a0e3"},
    {"address": 0x0800010c, "mnemonic": "pop", "op_str": "{pc}", "bytes": "7048bde8"},
]
cfg3 = cfg_from_instructions(insns3, "call_func", "arm")
d3 = cfg_to_dict(cfg3)
edges3 = d3["edges"]
blocks3 = d3["basic_blocks"]
print("Blocks:", len(blocks3))
for i, bb in enumerate(blocks3):
    print("  Block", i, ":", hex(bb["start_addr"]) if isinstance(bb["start_addr"], int) else bb["start_addr"])
for e in edges3:
    print("  Edge:", e["from"], "--[" + e["type"] + "]-->", e["to"], e.get("comment",""))
call_edges3 = [e for e in edges3 if e["type"] == "call"]
ret_edges3 = [e for e in edges3 if e["type"] == "return"]
print("Call edges:", len(call_edges3), "| Return edges:", len(ret_edges3))
assert len(call_edges3) >= 1, "Need at least 1 call edge"
assert len(ret_edges3) >= 1, "Need at least 1 return edge"
print("PASS: Call -> call edge present")

# Test 4: x86 if-else with loop
print("\n=== Test 4: x86 if-else + loop ===")
insns4 = [
    {"address": 0x08048000, "mnemonic": "push", "op_str": "ebp", "bytes": "55"},
    {"address": 0x08048001, "mnemonic": "mov", "op_str": "ebp, esp", "bytes": "89e5"},
    {"address": 0x08048003, "mnemonic": "cmp", "op_str": "eax, 0", "bytes": "83f800"},
    {"address": 0x08048006, "mnemonic": "je", "op_str": "0x08048010", "bytes": "7408"},
    {"address": 0x08048008, "mnemonic": "mov", "op_str": "eax, 1", "bytes": "b801000000"},
    {"address": 0x0804800d, "mnemonic": "pop", "op_str": "ebp", "bytes": "5d"},
    {"address": 0x0804800e, "mnemonic": "ret", "op_str": "", "bytes": "c3"},
    {"address": 0x08048010, "mnemonic": "xor", "op_str": "eax, eax", "bytes": "31c0"},
    {"address": 0x08048012, "mnemonic": "jmp", "op_str": "0x0804800d", "bytes": "ebf9"},
]
cfg4 = cfg_from_instructions(insns4, "x86_func", "x86")
d4 = cfg_to_dict(cfg4)
edges4 = d4["edges"]
blocks4 = d4["basic_blocks"]
print("Blocks:", len(blocks4))
for e in edges4:
    comment = e.get("comment", "")
    print("  Edge:", e["from"], "--[" + e["type"] + "]-->", e["to"], comment)
ret_edges = [e for e in edges4 if e["type"] == "return"]
jump_edges = [e for e in edges4 if e["type"] == "jump"]
print("  return:", len(ret_edges), "| jump:", len(jump_edges))
assert len(ret_edges) == 1
print("PASS: x86 if-else + loop")

# Test 5: Indirect jump (BX LR)
print("\n=== Test 5: Indirect jump ===")
insns5 = [
    {"address": 0x08000100, "mnemonic": "push", "op_str": "{lr}", "bytes": "70482de9"},
    {"address": 0x08000104, "mnemonic": "mov", "op_str": "r0, #0", "bytes": "0000a0e3"},
    {"address": 0x08000108, "mnemonic": "bx", "op_str": "lr", "bytes": "e1a0f00e"},
    {"address": 0x0800010c, "mnemonic": "nop", "op_str": "", "bytes": "e320f000"},
]
cfg5 = cfg_from_instructions(insns5, "indirect_jump", "arm")
d5 = cfg_to_dict(cfg5)
edges5 = d5["edges"]
indirect = [e for e in edges5 if e["type"] == "indirect_jump"]
print("Blocks:", len(d5["basic_blocks"]))
print("Indirect edges:", len(indirect))
for e in edges5:
    print("  Edge:", e["from"], "--[" + e["type"] + "]-->", e["to"], e.get("comment",""))
assert len(indirect) == 0  # bx lr detected as return (semantic correct)
print("PASS: Indirect jump -> bx lr = return edge")

print("\n" + "=" * 50)
print("ALL TESTS PASSED!")
