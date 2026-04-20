"""
Control Flow Graph (CFG) generation for disassembled functions.

Input:  disassembly instructions for a function
Output: structured CFG with basic blocks and control flow edges
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import struct

from capstone import Cs, CS_ARCH_ARM, CS_ARCH_ARM64, CS_ARCH_RISCV, CS_ARCH_X86, CS_MODE_ARM, CS_MODE_THUMB, CS_MODE_32, CS_MODE_64, CS_MODE_RISCV32, CS_MODE_RISCV64

# ═══════════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CFGInstruction:
    address: int
    mnemonic: str
    op_str: str
    bytes_hex: str = ""

@dataclass
class BasicBlock:
    start_addr: int
    end_addr: int
    instructions: list[int] = field(default_factory=list)
    preds: list[int] = field(default_factory=list)   # predecessor block indices
    succs: list[int] = field(default_factory=list)   # successor block indices

@dataclass
class CFGEdge:
    from_block: int
    to_block: int
    edge_type: str  # fallthrough | jump | conditional_true | conditional_false | call | return | indirect_jump
    comment: str = ""

@dataclass
class CFGResult:
    function_name: str
    basic_blocks: list[BasicBlock]
    edges: list[CFGEdge]
    entry_block: int
    arch: str
    stats: dict = field(default_factory=dict)

# ═══════════════════════════════════════════════════════════════════════════════
# Architecture configs
# ═══════════════════════════════════════════════════════════════════════════════

# Branch instructions per architecture
BRANCH_MNEMONICS = {
    "arm": {"b", "bl", "bx", "blx", "beq", "bne", "blt", "ble", "bgt", "bge",
             "bcc", "bcs", "bmi", "bpl", "bvs", "bvc", "bhi", "bls", "bal", "cbz", "cbnz"},
    "thumb": {"b", "bl", "bx", "blx", "beq", "bne", "blt", "ble", "bgt", "bge",
              "bcc", "bcs", "bmi", "bpl", "bvs", "bvc", "bhi", "bls", "bal", "cbz", "cbnz"},
    "arm64": {"b", "bl", "blr", "br", "ret", "cbnz", "cbz", "tbnz", "tbz",
               "b.eq", "b.ne", "b.lt", "b.le", "b.gt", "b.ge", "b.cc", "b.cs",
               "b.mi", "b.pl", "b.vs", "b.vc", "b.hi", "b.ls", "b.al"},
    "riscv": {"jal", "jalr", "beq", "bne", "blt", "bge", "bltu", "bgeu", "jr", "ret", "call"},
    "x86": {"jmp", "je", "jne", "jl", "jle", "jg", "jge", "jb", "jbe", "ja", "jae",
             "jo", "jno", "js", "jns", "loop", "loope", "loopne", "call", "ret", "int3"},
    "x86_64": {"jmp", "je", "jne", "jl", "jle", "jg", "jge", "jb", "jbe", "ja", "jae",
                "call", "ret", "syscall", "int3"},
}

# Unconditional branch / jump
UNCOND_BRANCH = {
    "arm": {"b", "bl", "blx", "bx", "bal"},
    "thumb": {"b", "bl", "blx", "bx", "bal"},
    "arm64": {"b", "bl", "blr", "br", "b.al"},
    "riscv": {"jal", "jalr", "jr", "call"},
    "x86": {"jmp", "call"},
    "x86_64": {"jmp", "call"},
}

# Return instructions
RETURN_MNEMONICS = {
    "arm": {"bx lr", "pop pc", "mov pc, lr", "ldr pc, [sp], #4", "v7"},
    "thumb": {"bx lr", "pop {pc}", "mov pc, lr", "v7"},
    "arm64": {"ret", "ret lr"},
    "riscv": {"ret", "jr ra"},
    "x86": {"ret", "retn", "retf", "iretd", "leave"},
    "x86_64": {"ret", "retn", "retf", "syscall"},
}

# Call instructions
CALL_MNEMONICS = {
    "arm": {"bl", "blx"},
    "thumb": {"bl", "blx"},
    "arm64": {"bl"},
    "riscv": {"jal", "jalr", "call"},
    "x86": {"call"},
    "x86_64": {"call"},
}

# Conditional branch mnemonics per arch (for x86-like syntax)
COND_BRANCH_ARM = {"beq", "bne", "blt", "ble", "bgt", "bge", "bcc", "bcs",
                     "bmi", "bpl", "bvs", "bvc", "bhi", "bls"}
COND_BRANCH_X86 = {"je", "jne", "jl", "jle", "jg", "jge", "jb", "jbe", "ja", "jae",
                    "jo", "jno", "js", "jns", "loop", "loope", "loopne"}


# ═══════════════════════════════════════════════════════════════════════════════
# CFG Generator
# ═══════════════════════════════════════════════════════════════════════════════

class CFGGenerator:
    """
    Generate a Control Flow Graph from a list of disassembly instructions.
    
    Algorithm:
    1. Linear scan to identify basic block boundaries
    2. Label every instruction address as belonging to a block
    3. Connect blocks with CFG edges
    4. Classify edges by type
    """
    
    def __init__(self, function_name: str, instructions: list[CFGInstruction], arch: str = "arm"):
        self.function_name = function_name
        self.instructions = instructions  # sorted by address
        self.arch = arch.lower()
        
        # Index: address -> instruction
        self.addr_to_insn: dict[int, CFGInstruction] = {
            insn.address: insn for insn in instructions
        }
        
        # Index: address -> block index
        self.addr_to_block: dict[int, int] = {}
        
        # Basic blocks
        self.blocks: list[BasicBlock] = []
        
        # Edges
        self.edges: list[CFGEdge] = []
        
        # Block start addresses (leaders)
        self.leaders: set[int] = {instructions[0].address} if instructions else set()
        
    def _is_return(self, insn: CFGInstruction) -> bool:
        """Check if instruction is a return."""
        mnemonic = insn.mnemonic.lower().strip()
        op = insn.op_str.lower().strip()
        
        # Exact matches
        if mnemonic == "ret":
            return True
        
        # ARM: bx lr, pop {pc}, mov pc, lr
        if self.arch in ("arm", "thumb"):
            if mnemonic == "bx" and "lr" in op:
                return True
            if mnemonic == "pop" and "pc" in op:
                return True
            if mnemonic == "mov" and "pc" in op and "lr" in op:
                return True
            if mnemonic == "ldr" and "pc" in op:
                return True
        
        # RISC-V: jr ra, ret
        if self.arch == "riscv":
            if mnemonic == "jr" and "ra" in op:
                return True
        
        # x86: ret, retn, retf, iret
        if self.arch in ("x86", "x86_64"):
            if mnemonic.startswith("ret"):
                return True
            if mnemonic in ("iretd", "iretw", "iretf"):
                return True
        
        return False
    
    def _is_call(self, insn: CFGInstruction) -> bool:
        """Check if instruction is a call."""
        mnemonic = insn.mnemonic.lower().strip()
        
        if self.arch in ("arm", "thumb"):
            return mnemonic in ("bl", "blx", "blz")  # BLX can be both
        
        if self.arch == "arm64":
            return mnemonic == "bl"
        
        if self.arch == "riscv":
            return mnemonic in ("jal", "jalr")
        
        if self.arch in ("x86", "x86_64"):
            return mnemonic == "call"
        
        return False
    
    def _is_branch(self, insn: CFGInstruction) -> bool:
        """Check if instruction is a branch/jump."""
        mnemonic = insn.mnemonic.lower().strip()
        
        branch_set = BRANCH_MNEMONICS.get(self.arch, set())
        if mnemonic in branch_set:
            return True
        
        # arm64 dot-notation: b.eq, b.ne, etc.
        if self.arch in ("arm", "arm64", "thumb"):
            if mnemonic.startswith("b."):
                return True
        
        # x86: any instruction starting with 'j' (jmp, je, jne, etc.)
        if self.arch in ("x86", "x86_64"):
            if mnemonic.startswith("j"):
                return True
        
        return False
    
    def _is_conditional(self, insn: CFGInstruction) -> bool:
        """Check if branch is conditional."""
        mnemonic = insn.mnemonic.lower().strip()
        op = insn.op_str.lower().strip()
        
        if self.arch in ("arm", "thumb"):
            # ARM dot-notation: b.eq, b.ne, etc.
            if mnemonic.startswith("b."):
                return True
            # CBZ/CBNZ are conditional branches
            if mnemonic.startswith("cb"):
                return True
            # Old-style conditional: beq, bne, blt, etc. (but NOT bl, b, bx, blx, bal)
            uncond = UNCOND_BRANCH.get(self.arch, set())
            if mnemonic in BRANCH_MNEMONICS.get(self.arch, set()) and mnemonic not in uncond:
                return True
            return False
        
        if self.arch in ("x86", "x86_64"):
            # All 'j' except 'jmp' are conditional
            if mnemonic.startswith("j") and mnemonic != "jmp":
                return True
            # loop variants are conditional
            if mnemonic.startswith("loop"):
                return True
        
        if self.arch == "arm64":
            if mnemonic.startswith("b."):
                return True
            if mnemonic.startswith("cbn") or mnemonic.startswith("tbn") or mnemonic.startswith("cbz"):
                return True
        
        if self.arch == "riscv":
            # All b* except jal/jalr are conditional branches
            if mnemonic.startswith("b") and mnemonic not in ("bal",):
                return True
        
        return False
    
    def _is_indirect(self, insn: CFGInstruction) -> bool:
        """Check if branch is indirect (target not known statically)."""
        mnemonic = insn.mnemonic.lower().strip()
        op = insn.op_str.strip()
        
        # No immediate operand = indirect
        if not op or op == "":
            return True
        
        # Immediate with register = indirect
        if self.arch in ("arm", "thumb"):
            if mnemonic in ("bx", "blr", "br"):
                return True
        
        if self.arch == "arm64":
            if mnemonic in ("br", "blr", "ret"):
                return True
        
        if self.arch == "riscv":
            if mnemonic in ("jr",):
                return True
        
        if self.arch in ("x86", "x86_64"):
            if mnemonic == "jmp" and not op.startswith("0x"):
                return True
            if mnemonic == "call" and not op.startswith("0x"):
                return True
        
        return False
    
    def _parse_jump_target(self, insn: CFGInstruction) -> Optional[int]:
        """Parse immediate jump target address from operand."""
        op = insn.op_str.strip()
        if not op:
            return None
        
        # Hex address
        if op.startswith("0x") or op.startswith("0X"):
            try:
                return int(op, 16)
            except ValueError:
                pass
        
        # Label name -> can't resolve statically
        return None
    
    def _compute_block_boundaries(self) -> list:
        """
        Compute basic block boundaries.
        
        Algorithm:
        1. Mark leaders: entry + targets of branches/jumps + fall-through after
           branches/jumps/returns.
        2. A block ends at: return, unconditional branch, conditional branch.
        
        Returns:
            List of (start_addr, end_addr, start_idx, end_idx)
        """
        if not self.instructions:
            return []
        
        # Mark leaders: addr -> reason
        leaders: dict[int, str] = {self.instructions[0].address: "entry"}
        
        for i, insn in enumerate(self.instructions):
            is_return = self._is_return(insn)
            is_call = self._is_call(insn)
            is_branch = self._is_branch(insn) and not is_call
            is_cond = self._is_conditional(insn)
            
            if is_return or is_branch or is_call:
                # This instruction ends the current block.
                # Fall-through (next instruction after branch/return/call) starts a new block.
                if i + 1 < len(self.instructions):
                    next_addr = self.instructions[i + 1].address
                    if next_addr not in leaders:
                        leaders[next_addr] = "fallthrough"
                
                # For branches with a known target, the target is also a leader.
                if not is_cond:
                    # Unconditional: only target is a leader (no fall-through)
                    target = self._parse_jump_target(insn)
                    if target is not None and target in self.addr_to_insn:
                        leaders[target] = "jump_target"
                else:
                    # Conditional: both target and fall-through are leaders
                    target = self._parse_jump_target(insn)
                    if target is not None and target in self.addr_to_insn:
                        leaders[target] = "branch_target"
        
        # Sort leaders
        leaders_sorted = sorted(leaders.keys())
        blocks = []
        
        for i, leader_addr in enumerate(leaders_sorted):
            # Find start index in instructions
            start_idx = next(
                j for j, insn in enumerate(self.instructions) if insn.address == leader_addr
            )
            
            # Determine end: last instruction BEFORE the next leader.
            # Leaders are block STARTS, so current block ends right before
            # the next leader's address. Start search from start_idx+1.
            if i + 1 < len(leaders_sorted):
                next_leader_addr = leaders_sorted[i + 1]
                end_idx = start_idx  # default: single instruction block
                for j in range(start_idx + 1, len(self.instructions)):
                    if self.instructions[j].address >= next_leader_addr:
                        end_idx = j - 1
                        break
                else:
                    end_idx = len(self.instructions) - 1
            else:
                end_idx = len(self.instructions) - 1
            
            block_insns = self.instructions[start_idx:end_idx + 1]
            blocks.append((
                leader_addr,
                block_insns[-1].address if block_insns else leader_addr,
                start_idx,
                end_idx,
            ))
        
        return blocks
    
    def _build_blocks(self, block_bounds: list) -> None:
        """Build BasicBlock objects from computed boundaries."""
        self.blocks = []
        
        for start_addr, end_addr, start_idx, end_idx in block_bounds:
            block_insns = [self.instructions[i].address for i in range(start_idx, end_idx + 1)]
            block = BasicBlock(
                start_addr=start_addr,
                end_addr=end_addr,
                instructions=block_insns,
            )
            self.blocks.append(block)
            
            # Map each instruction address to this block
            for addr in block_insns:
                self.addr_to_block[addr] = len(self.blocks) - 1
    
    def _build_edges(self) -> None:
        """Build CFG edges from block structure."""
        self.edges = []
        
        for block_idx, block in enumerate(self.blocks):
            if not block.instructions:
                continue
            
            last_insn_addr = block.instructions[-1]
            last_insn = self.addr_to_insn.get(last_insn_addr)
            
            if last_insn is None:
                continue
            
            # Return: emit a return edge
            if self._is_return(last_insn):
                self.edges.append(CFGEdge(
                    from_block=block_idx,
                    to_block=-1,
                    edge_type="return",
                    comment=f"return via {last_insn.mnemonic}",
                ))
                continue
            
            # Call instruction: call edge + fall-through return edge
            # (MUST check before branch, since bl/blx are in BRANCH_MNEMONICS too)
            if self._is_call(last_insn):
                target = self._parse_jump_target(last_insn)
                
                if target is not None and target in self.addr_to_block:
                    self.edges.append(CFGEdge(
                        from_block=block_idx,
                        to_block=self.addr_to_block[target],
                        edge_type="call",
                        comment=f"call to 0x{target:x}",
                    ))
                else:
                    # Call with unknown target (indirect call)
                    self.edges.append(CFGEdge(
                        from_block=block_idx,
                        to_block=-1,
                        edge_type="call",
                        comment=f"call via {last_insn.mnemonic} (target unknown)",
                    ))
                
                # Fall-through (return from call)
                if block_idx + 1 < len(self.blocks):
                    self.edges.append(CFGEdge(
                        from_block=block_idx,
                        to_block=block_idx + 1,
                        edge_type="fallthrough",
                        comment="return from call (fall-through)",
                    ))
                continue
            
            # Unconditional branch / jump (non-call)
            if self._is_branch(last_insn) and not self._is_conditional(last_insn):
                target = self._parse_jump_target(last_insn)
                
                if target is not None and target in self.addr_to_block:
                    # Direct jump
                    target_idx = self.addr_to_block[target]
                    self.edges.append(CFGEdge(
                        from_block=block_idx,
                        to_block=target_idx,
                        edge_type="jump",
                        comment=f"jump to 0x{target:x}",
                    ))
                elif self._is_indirect(last_insn):
                    # Indirect jump (register-based, can't resolve statically)
                    self.edges.append(CFGEdge(
                        from_block=block_idx,
                        to_block=-1,
                        edge_type="indirect_jump",
                        comment=f"indirect jump (target unknown) via {last_insn.mnemonic} {last_insn.op_str}",
                    ))
                else:
                    # Jump target outside loaded code
                    self.edges.append(CFGEdge(
                        from_block=block_idx,
                        to_block=-1,
                        edge_type="indirect_jump",
                        comment=f"jump target 0x{target:x} outside loaded range",
                    ))
                continue
            
            # Conditional branch: two edges (taken/not-taken)
            if self._is_conditional(last_insn):
                target = self._parse_jump_target(last_insn)
                
                # Fall-through (not taken)
                if block_idx + 1 < len(self.blocks):
                    self.edges.append(CFGEdge(
                        from_block=block_idx,
                        to_block=block_idx + 1,
                        edge_type="conditional_false",
                        comment=f"branch not taken (fall-through)",
                    ))
                
                # Taken (conditional true)
                if target is not None and target in self.addr_to_block:
                    self.edges.append(CFGEdge(
                        from_block=block_idx,
                        to_block=self.addr_to_block[target],
                        edge_type="conditional_true",
                        comment=f"branch taken to 0x{target:x}",
                    ))
                elif self._is_indirect(last_insn):
                    self.edges.append(CFGEdge(
                        from_block=block_idx,
                        to_block=-1,
                        edge_type="indirect_jump",
                        comment=f"indirect branch via {last_insn.mnemonic}",
                    ))
                continue
            
            # Normal fall-through (no branch)
            if block_idx + 1 < len(self.blocks):
                self.edges.append(CFGEdge(
                    from_block=block_idx,
                    to_block=block_idx + 1,
                    edge_type="fallthrough",
                ))
    
    def _compute_preds(self) -> None:
        """Compute predecessor lists for each block."""
        for block in self.blocks:
            block.preds.clear()
        
        for edge in self.edges:
            if edge.to_block >= 0 and edge.to_block < len(self.blocks):
                if edge.from_block not in self.blocks[edge.to_block].preds:
                    self.blocks[edge.to_block].preds.append(edge.from_block)
    
    def generate(self) -> CFGResult:
        """Generate the complete CFG."""
        if not self.instructions:
            return CFGResult(
                function_name=self.function_name,
                basic_blocks=[],
                edges=[],
                entry_block=0,
                arch=self.arch,
                stats={"total_instructions": 0, "total_blocks": 0, "total_edges": 0},
            )
        
        # Build CFG
        block_bounds = self._compute_block_boundaries()
        self._build_blocks(block_bounds)
        self._build_edges()
        self._compute_preds()
        
        # Find entry block (usually block with lowest address)
        entry_block = 0
        if self.blocks:
            entry_block = min(
                range(len(self.blocks)),
                key=lambda i: (self.blocks[i].start_addr, i)
            )
        
        # Compute stats
        edge_types: dict[str, int] = {}
        for edge in self.edges:
            edge_types[edge.edge_type] = edge_types.get(edge.edge_type, 0) + 1
        
        return CFGResult(
            function_name=self.function_name,
            basic_blocks=self.blocks,
            edges=self.edges,
            entry_block=entry_block,
            arch=self.arch,
            stats={
                "total_instructions": len(self.instructions),
                "total_blocks": len(self.blocks),
                "total_edges": len(self.edges),
                "edge_types": edge_types,
            },
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience: From raw disasm lines to CFG
# ═══════════════════════════════════════════════════════════════════════════════

def cfg_from_instructions(
    instructions: list[dict],
    function_name: str = "unknown",
    arch: str = "arm",
) -> CFGResult:
    """
    Build CFG from a list of instruction dicts.
    
    Args:
        instructions: list of dicts with keys: address (int or hex str), mnemonic, op_str, bytes (optional)
        function_name: name of the function
        arch: target architecture
    
    Returns:
        CFGResult object
    """
    parsed = []
    for item in instructions:
        addr = item["address"]
        if isinstance(addr, str):
            addr = int(addr, 16)
        elif isinstance(addr, int):
            addr = addr
        
        parsed.append(CFGInstruction(
            address=addr,
            mnemonic=str(item.get("mnemonic", "")).strip(),
            op_str=str(item.get("op_str", "")).strip(),
            bytes_hex=str(item.get("bytes", item.get("bytes_hex", ""))).strip(),
        ))
    
    # Sort by address
    parsed.sort(key=lambda x: x.address)
    
    gen = CFGGenerator(function_name, parsed, arch)
    return gen.generate()


def cfg_to_dict(cfg: CFGResult) -> dict:
    """Serialize CFGResult to JSON-friendly dict."""
    return {
        "function_name": cfg.function_name,
        "basic_blocks": [
            {
                "start_addr": hex(b.start_addr),
                "end_addr": hex(b.end_addr),
                "instructions": [hex(a) for a in b.instructions],
            }
            for b in cfg.basic_blocks
        ],
        "edges": [
            {
                "from": e.from_block,
                "to": e.to_block,
                "type": e.edge_type,
                "comment": e.comment,
            }
            for e in cfg.edges
        ],
        "entry_block": cfg.entry_block,
        "stats": cfg.stats,
    }
