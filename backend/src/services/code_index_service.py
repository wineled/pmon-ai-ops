"""
Code Index & Retrieval Service
Builds an in-memory index of local source code for LLM context retrieval.

Architecture:
  - Index all source files (Python/C/etc.) by content chunks
  - Keyword + BM25-style retrieval for relevant chunks
  - Returns ranked code snippets with file:line references

Usage:
  - build_index(code_dir)  → builds/updates the index
  - retrieve(query, top_k=10)  → returns relevant code chunks
"""

from __future__ import annotations

import re
import os
import mmap
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import struct

import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CodeChunk:
    """A chunk of source code with metadata."""
    chunk_id: str
    file_path: str
    line_start: int      # 1-based line number
    line_end: int
    content: str
    function_name: str = ""
    language: str = ""

    @property
    def ref(self) -> str:
        return f"{self.file_path}:{self.line_start}-{self.line_end}"

    @property
    def lines(self) -> int:
        return self.line_end - self.line_start + 1

    def snippet(self, context_lines: int = 3) -> str:
        """Return a short snippet with surrounding context."""
        lines = self.content.splitlines(keepends=True)
        # Show first few lines as preview
        preview = "".join(lines[:context_lines])
        if len(self.content) > 200:
            preview += "..."
        return preview


@dataclass
class RetrievalResult:
    """A retrieved code chunk with relevance score."""
    chunk: CodeChunk
    score: float
    matched_keywords: list[str] = field(default_factory=list)
    relevance_label: str = "related"  # core | related | peripheral


@dataclass
class IndexStats:
    """Statistics about the code index."""
    total_files: int
    total_chunks: int
    total_lines: int
    total_size_bytes: int
    languages: dict[str, int]  # language → file count
    indexed_at: str


# ──────────────────────────────────────────────────────────────────────────────
# Token counter (rough, no external deps)
# ──────────────────────────────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, 2 for Chinese."""
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_like = len(re.findall(r"[a-zA-Z0-9_ \t.,;:]+", text))
    other = len(text) - chinese - ascii_like
    return (ascii_like + chinese * 2 + other * 2) // 4


CHUNK_MAX_TOKENS = 512      # ~2000 chars per chunk
CHUNK_OVERLAP = 50          # lines overlap for context
MIN_CHUNK_LINES = 5


# ──────────────────────────────────────────────────────────────────────────────
# Code Index
# ──────────────────────────────────────────────────────────────────────────────

class CodeIndex:
    """
    In-memory code index for fast retrieval.
    
    Supports:
    - File globbing and parsing (Python, C, C++, JavaScript, etc.)
    - Function-level chunking
    - Keyword extraction and BM25-style scoring
    - Retrieval by query string
    """

    # File extensions to index
    INDEXED_EXTENSIONS = {
        ".py", ".c", ".h", ".cpp", ".hpp", ".cc", ".js", ".ts",
        ".jsx", ".tsx", ".go", ".rs", ".java", ".cs", ".rb", ".php",
        ".sh", ".bash", ".ps1", ".bat", ".cmake", ".mk", ".s", ".S",
        ".asm", ".vue", ".svelte", ".yaml", ".yml", ".toml", ".ini",
        ".cfg", ".conf", ".json", ".xml", ".html", ".css", ".scss",
    }

    # Directories to skip
    SKIP_DIRS = {
        "__pycache__", ".git", ".svn", ".hg", "node_modules",
        "venv", "env", ".venv", ".env", "build", "dist", ".dist",
        "target", ".pytest_cache", ".mypy_cache", ".tox", "coverage",
        ".next", ".nuxt", ".cache", ".tmp", "temp", "tmp",
        ".venv310", "site-packages", "node_modules",
    }

    # Directories to index (top-level relative paths)
    DEFAULT_CODE_DIRS = [
        "../",           # sibling to backend/
        "../../",        # project root
    ]

    def __init__(self, code_root: Optional[str] = None):
        self.code_root = code_root
        self.chunks: list[CodeChunk] = []
        self.chunk_index: dict[str, int] = {}  # chunk_id → index
        self.file_chunks: dict[str, list[int]] = {}  # file_path → [chunk_ids]
        self._keywords: list[str] = []  # global keyword list
        self._doc_freq: dict[str, int] = {}  # keyword → doc frequency
        self.stats: Optional[IndexStats] = None

    # ── Building ────────────────────────────────────────────────────────────────

    def build(self, code_paths: list[str] | None = None) -> IndexStats:
        """
        Build or rebuild the full code index.
        
        Args:
            code_paths: List of directories/files to index. 
                        Defaults to DEFAULT_CODE_DIRS.
        """
        import time
        t0 = time.time()
        
        self.chunks.clear()
        self.chunk_index.clear()
        self.file_chunks.clear()
        self._keywords.clear()
        self._doc_freq.clear()

        paths = code_paths or self.DEFAULT_CODE_DIRS
        if isinstance(paths, str):
            paths = [paths]

        all_files: list[str] = []
        for p in paths:
            resolved = self._resolve_path(p)
            if resolved:
                all_files.extend(self._collect_files(resolved))

        logger.info(f"[CodeIndex] Found {len(all_files)} files to index")

        total_lines = 0
        total_size = 0
        languages: dict[str, int] = {}

        for file_path in all_files:
            try:
                file_chunks = self._index_file(file_path)
                if file_chunks:
                    self.file_chunks[file_path] = [c.chunk_id for c in file_chunks]
                    for chunk in file_chunks:
                        idx = len(self.chunks)
                        self.chunk_index[chunk.chunk_id] = idx
                        self.chunks.append(chunk)
                    
                    # Language detection
                    ext = Path(file_path).suffix
                    lang = self._ext_to_lang(ext)
                    languages[lang] = languages.get(lang, 0) + 1
                    
                    # Stats
                    total_lines += sum(c.lines for c in file_chunks)
                    total_size += os.path.getsize(file_path)
            except Exception as e:
                logger.debug(f"[CodeIndex] Skipped {file_path}: {e}")

        # Build keyword statistics
        self._build_keyword_stats()

        elapsed = time.time() - t0
        self.stats = IndexStats(
            total_files=len(all_files),
            total_chunks=len(self.chunks),
            total_lines=total_lines,
            total_size_bytes=total_size,
            languages=languages,
            indexed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        
        logger.info(
            f"[CodeIndex] Built in {elapsed:.1f}s: "
            f"{len(self.chunks)} chunks, {total_lines:,} lines, "
            f"{total_size/1024/1024:.1f} MB"
        )
        return self.stats

    def _resolve_path(self, p: str) -> Optional[str]:
        """Resolve a path relative to code_root or absolute."""
        if os.path.isabs(p):
            return p if os.path.exists(p) else None
        
        # Try relative to code_root
        if self.code_root and os.path.exists(os.path.join(self.code_root, p)):
            return os.path.join(self.code_root, p)
        
        # Try as absolute
        if os.path.exists(p):
            return p
        return None

    def _collect_files(self, root: str) -> list[str]:
        """Recursively collect all indexable files."""
        files = []
        
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skip directories
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]
            
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.INDEXED_EXTENSIONS:
                    # Skip obviously auto-generated files
                    if any(kw in fname for kw in ["_generated", ".min.", ".bundle.", "dist/"]):
                        continue
                    files.append(fpath)
        
        return files

    def _index_file(self, file_path: str) -> list[CodeChunk]:
        """Parse a single file into code chunks."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return []

        if not content.strip():
            return []

        rel_path = os.path.relpath(file_path, os.getcwd())
        lang = self._ext_to_lang(Path(file_path).suffix.lower())
        chunks = []

        # Try function-level chunking first
        func_chunks = self._chunk_by_functions(
            content, rel_path, lang
        )
        if func_chunks:
            chunks.extend(func_chunks)
        else:
            # Fall back to line-based chunking
            chunks.extend(self._chunk_by_lines(content, rel_path, lang))

        return chunks

    def _chunk_by_functions(
        self, content: str, file_path: str, lang: str
    ) -> list[CodeChunk]:
        """Split file into function-level chunks."""
        lines = content.splitlines(keepends=True)
        if len(lines) < MIN_CHUNK_LINES:
            return []

        # Function patterns per language
        func_patterns = [
            # Python
            r"^\s*(?:def|async\s+def)\s+(\w+)",
            r"^\s*class\s+(\w+)",
            # C/C++/Java/JS/TS
            r"^\s*(?:static\s+)?(?:inline\s+)?(?:const\s+)?"
            r"(?:\w+(?:\s*\*\s*|\s+))"  # return type
            r"(\w+)\s*\(",           # function name
            r"^\s*(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?"
            r"(?:\w+(?:\s*\*\s*)?\s+)"  # return type
            r"(\w+)\s*\(",
            # Go
            r"^\s*func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(",
            # Rust
            r"^\s*(?:pub\s+)?(?:async\s+)?(?:unsafe\s+)?(?:extern\s+)?"
            r"(?:fn|pub fn|async fn)\s+(\w+)",
            # Shell
            r"^\s*function\s+(\w+)",
            r"^\s*(\w+)\s*\(\)\s*\{",
        ]

        import re
        func_pattern = None
        for pat in func_patterns:
            if re.match(pat.replace(r"^\s*", "").replace(r"\\s+", ""), 
                       lines[0] if lines else ""):
                func_pattern = re.compile(pat, re.MULTILINE)
                break

        if not func_pattern:
            # Try all patterns
            for pat in func_patterns:
                cp = re.compile(pat, re.MULTILINE)
                if cp.search(content):
                    func_pattern = cp
                    break

        if not func_pattern:
            return []

        # Find function boundaries
        func_starts: list[tuple[int, str]] = []  # (line_idx, func_name)
        prev_func_end = 0
        prev_name = "<module>"

        for m in func_pattern.finditer(content):
            func_name = m.group(1) if m.groups() else f"<fn_{len(func_starts)}>"
            # Find line number
            line_num = content[:m.start()].count("\n") + 1
            func_starts.append((line_num, func_name))

        if not func_starts:
            return []

        # Build chunks for each function
        result = []
        for i, (start_line, func_name) in enumerate(func_starts):
            end_line = (
                func_starts[i + 1][0] - 1
                if i + 1 < len(func_starts)
                else len(lines)
            )
            chunk_lines = "".join(lines[start_line - 1:end_line])
            
            if len(chunk_lines.strip()) < 20:
                continue

            chunk_id = self._make_chunk_id(file_path, start_line, func_name)
            chunk = CodeChunk(
                chunk_id=chunk_id,
                file_path=file_path,
                line_start=start_line,
                line_end=end_line,
                content=chunk_lines,
                function_name=func_name,
                language=lang,
            )
            result.append(chunk)

        return result

    def _chunk_by_lines(
        self, content: str, file_path: str, lang: str
    ) -> list[CodeChunk]:
        """Split file into fixed-size line chunks."""
        lines = content.splitlines(keepends=True)
        chunks = []
        
        # Target ~100 lines per chunk (adjust for token limit)
        target_lines = min(100, max(20, CHUNK_MAX_TOKENS // 10))
        i = 0
        chunk_num = 0
        
        while i < len(lines):
            chunk_lines = lines[i : i + target_lines]
            chunk_content = "".join(chunk_lines)
            start_line = i + 1
            end_line = i + len(chunk_lines)
            
            chunk_id = self._make_chunk_id(file_path, start_line, f"chunk_{chunk_num}")
            chunk = CodeChunk(
                chunk_id=chunk_id,
                file_path=file_path,
                line_start=start_line,
                line_end=end_line,
                content=chunk_content,
                language=lang,
            )
            chunks.append(chunk)
            
            i += target_lines - CHUNK_OVERLAP
            chunk_num += 1

        return chunks

    def _make_chunk_id(self, file_path: str, line_start: int, suffix: str) -> str:
        """Generate a unique chunk ID."""
        key = f"{file_path}:{line_start}:{suffix}"
        return hashlib.md5(key.encode()).hexdigest()[:16]

    def _build_keyword_stats(self) -> None:
        """Build keyword frequency statistics for BM25 scoring."""
        import re
        word_freq: dict[str, int] = {}
        doc_count = len(self.chunks)
        
        # Simple tokenizer
        word_pat = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b")
        
        for chunk in self.chunks:
            words = set(word_pat.findall(chunk.content.lower()))
            for w in words:
                word_freq[w] = word_freq.get(w, 0) + 1
        
        self._doc_freq = word_freq
        self._keywords = sorted(word_freq.keys())
        
        # Precompute IDF for all words
        self._idf: dict[str, float] = {}
        avg_dl = sum(len(c.content.split()) for c in self.chunks) / max(doc_count, 1)
        for word, df in word_freq.items():
            # BM25 IDF formula
            self._idf[word] = max(
                0, 0.5 + 0.5 * df / max(df - 1, 1)
            ) if df > 1 else 0.5

    # ── Retrieval ──────────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        max_tokens: int = 8192,
        lang_filter: str | None = None,
    ) -> list[RetrievalResult]:
        """
        Retrieve the most relevant code chunks for a query.
        
        Uses BM25-style keyword scoring + function name matching.
        
        Args:
            query: Natural language search query
            top_k: Maximum number of chunks to return
            max_tokens: Approximate token budget for returned chunks
            lang_filter: Optional language filter (e.g., "python", "c")
        
        Returns:
            Ranked list of RetrievalResult objects
        """
        import re
        
        if not self.chunks:
            return []
        
        # Tokenize query
        word_pat = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b")
        query_words = set(word_pat.findall(query.lower()))
        
        # Also extract quoted strings and special terms
        for m in re.finditer(r'"([^"]+)"', query):
            query_words.update(m.group(1).lower().split())
        for m in re.finditer(r"'([^']+)'", query):
            query_words.update(m.group(1).lower().split())
        
        if not query_words:
            return []

        scores: dict[str, tuple[float, list[str]]] = {}
        avg_dl = sum(len(c.content.split()) for c in self.chunks) / len(self.chunks)
        k1, b = 1.5, 0.75  # BM25 parameters
        
        for chunk in self.chunks:
            if lang_filter and chunk.language != lang_filter:
                continue
            
            chunk_words = set(word_pat.findall(chunk.content.lower()))
            matched = query_words & chunk_words
            
            if not matched:
                # Partial match on function names
                fn_lower = chunk.function_name.lower() if chunk.function_name else ""
                if fn_lower and any(q in fn_lower for q in query_words):
                    matched = query_words & set(fn_lower.split("_"))
            
            if not matched:
                continue
            
            # BM25 score
            dl = len(chunk.content.split())
            score = 0.0
            for word in matched:
                tf = chunk_words.count(word)
                idf = self._idf.get(word, 0.5)
                score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
            
            # Boost: function name match
            if chunk.function_name:
                fn_match = sum(1 for q in query_words if q in chunk.function_name.lower())
                score += fn_match * 5.0
            
            # Boost: error-related keywords
            error_boost = sum(
                1 for kw in matched 
                if kw in {"error", "fail", "exception", "crash", "bug", "fix", "warn"}
            )
            score += error_boost * 3.0
            
            if chunk.file_path not in scores or scores[chunk.file_path][0] < score:
                scores[chunk.file_path] = (score, list(matched))
        
        # Rank and build results
        ranked = sorted(scores.items(), key=lambda x: -x[1][0])
        
        results: list[RetrievalResult] = []
        used_tokens = 0
        
        for file_path, (score, matched) in ranked:
            # Find the best chunk for this file (largest score)
            best_chunk = max(
                (c for c in self.chunks if c.file_path == file_path),
                key=lambda c: sum(
                    1 for w in matched if w in c.content.lower()
                ),
                default=None,
            )
            if not best_chunk:
                continue
            
            chunk_tokens = count_tokens(best_chunk.content)
            if used_tokens + chunk_tokens > max_tokens:
                continue
            
            used_tokens += chunk_tokens
            
            # Determine relevance label
            if score > 20:
                label = "core"
            elif score > 5:
                label = "related"
            else:
                label = "peripheral"
            
            results.append(RetrievalResult(
                chunk=best_chunk,
                score=round(score, 2),
                matched_keywords=list(matched),
                relevance_label=label,
            ))
            
            if len(results) >= top_k:
                break
        
        return results

    def get_context_for_llm(
        self,
        query: str,
        max_tokens: int = 8192,
        lang_filter: str | None = None,
    ) -> str:
        """
        Build a code context string for LLM consumption.
        
        Returns a formatted string with file references and code snippets.
        """
        results = self.retrieve(query, top_k=10, max_tokens=max_tokens, lang_filter=lang_filter)
        
        if not results:
            return "/* No relevant code found for query */"
        
        lines = [
            "/* =========================================================",
            "  CODE CONTEXT (Auto-retrieved)",
            f"  Query: {query[:100]}",
            f"  Results: {len(results)} chunks",
            "========================================================== */",
            "",
        ]
        
        current_file = ""
        for r in results:
            chunk = r.chunk
            if chunk.file_path != current_file:
                lines.append(f'\n/* ── {chunk.file_path} ── */')
                current_file = chunk.file_path
            
            lines.append(
                f'\n/* [{r.relevance_label}] score={r.score} '
                f'lines={chunk.line_start}-{chunk.line_end} '
                f'fn={chunk.function_name or "?"} '
                f'keywords={", ".join(r.matched_keywords)} */'
            )
            lines.append(chunk.content)
        
        return "\n".join(lines)

    @staticmethod
    def _ext_to_lang(ext: str) -> str:
        """Map file extension to language name."""
        lang_map = {
            ".py": "python", ".c": "c", ".h": "c",
            ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
            ".js": "javascript", ".ts": "typescript",
            ".jsx": "jsx", ".tsx": "tsx",
            ".go": "go", ".rs": "rust", ".java": "java",
            ".cs": "csharp", ".rb": "ruby", ".php": "php",
            ".sh": "shell", ".bash": "bash", ".ps1": "powershell",
            ".s": "asm", ".S": "asm", ".asm": "asm",
            ".vue": "vue", ".yaml": "yaml", ".yml": "yaml",
            ".toml": "toml", ".json": "json", ".xml": "xml",
            ".html": "html", ".css": "css", ".scss": "scss",
        }
        return lang_map.get(ext, ext.lstrip(".").lower())


# ──────────────────────────────────────────────────────────────────────────────
# Global singleton (lazy initialization)
# ──────────────────────────────────────────────────────────────────────────────

_code_index: CodeIndex | None = None


def get_code_index() -> CodeIndex:
    """Get or create the global code index singleton."""
    global _code_index
    if _code_index is None:
        _code_index = CodeIndex()
    return _code_index


def build_code_index(code_paths: list[str] | None = None) -> IndexStats:
    """Build/rebuild the global code index."""
    index = get_code_index()
    return index.build(code_paths)
