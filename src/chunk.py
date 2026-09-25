"""src/chunk.py — overlapping-chunk splitting for source files."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str       # this chunk's own source text
    start_line: int  # 1-based ABSOLUTE line number of this chunk's first line in the file
    end_line: int    # 1-based ABSOLUTE line number of this chunk's last line in the file
    index: int       # 0-based position of this chunk within the file


def chunk_text(source: str, chunk_lines: int = 300, overlap_lines: int = 30) -> list[Chunk]:
    """Split source into overlapping chunks. Returns [] for empty source."""
    if chunk_lines < 1:
        raise ValueError(f"chunk_lines must be >= 1, got {chunk_lines}")
    if not (0 <= overlap_lines < chunk_lines):
        raise ValueError(
            f"overlap_lines must satisfy 0 <= overlap_lines < chunk_lines, "
            f"got overlap_lines={overlap_lines}, chunk_lines={chunk_lines}"
        )

    if not source:
        return []

    all_lines = source.splitlines()
    total = len(all_lines)

    step = chunk_lines - overlap_lines
    chunks: list[Chunk] = []
    index = 0
    start = 0  # 0-based index into all_lines

    while start < total:
        end = min(start + chunk_lines, total)  # exclusive, 0-based
        # Reconstruct the text for these lines.  Line counting is pinned to
        # str.splitlines(), and the invariant this module guarantees is that
        # text.splitlines() reconstructs exactly the source lines for the
        # declared span (start_line..end_line).  A bare "\n".join(slice) does
        # not satisfy that for every slice, so the terminal newline below is
        # load-bearing rather than cosmetic -- keep it.
        chunk_lines_list = all_lines[start:end]
        text = "\n".join(chunk_lines_list) + "\n"
        start_line = start + 1        # convert to 1-based
        end_line = end                # end is already the 1-based last line (end-1+1)
        chunks.append(Chunk(text=text, start_line=start_line, end_line=end_line, index=index))
        index += 1
        if end == total:
            break
        start += step

    return chunks


def to_absolute(chunk: Chunk, relative_line: int) -> int:
    """Map a 1-based line number RELATIVE to `chunk` into an ABSOLUTE line number."""
    max_relative = chunk.end_line - chunk.start_line + 1
    if not (1 <= relative_line <= max_relative):
        raise ValueError(
            f"relative_line {relative_line} is out of range [1, {max_relative}] "
            f"for chunk at lines {chunk.start_line}..{chunk.end_line}"
        )
    return chunk.start_line + relative_line - 1


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    failures = 0

    def check(label: str, condition: bool) -> None:
        global failures
        status = "PASS" if condition else "FAIL"
        if not condition:
            failures += 1
        print(f"{status}: {label}")

    def raised(fn) -> bool:
        try:
            fn()
            return False
        except (ValueError, TypeError):
            return True

    # --- to_absolute mapping ---
    # Use a source with more than one chunk so line numbers are non-trivial.
    src = "\n".join(f"line{i}" for i in range(1, 101))  # 100 lines
    chunks = chunk_text(src, chunk_lines=40, overlap_lines=10)
    # chunk[0]: lines 1..40, chunk[1]: lines 31..70, chunk[2]: lines 61..100
    c0, c1, c2 = chunks[0], chunks[1], chunks[2]

    check("to_absolute: chunk0, relative 1 -> absolute 1",  to_absolute(c0, 1) == 1)
    check("to_absolute: chunk0, relative 40 -> absolute 40", to_absolute(c0, 40) == 40)
    check("to_absolute: chunk1, relative 1 -> absolute 31",  to_absolute(c1, 1) == 31)
    check("to_absolute: chunk1, relative 10 -> absolute 40", to_absolute(c1, 10) == 40)
    check("to_absolute: chunk2, relative 1 -> absolute 61",  to_absolute(c2, 1) == 61)
    check("to_absolute: chunk2, relative 40 -> absolute 100", to_absolute(c2, 40) == 100)
    check("to_absolute: out-of-range raises ValueError",    raised(lambda: to_absolute(c0, 41)))
    check("to_absolute: zero raises ValueError",            raised(lambda: to_absolute(c0, 0)))

    # --- overlap arithmetic ---
    check("overlap: chunk0 start_line=1",  c0.start_line == 1)
    check("overlap: chunk1 start_line=31", c1.start_line == 31)  # step = 40-10 = 30
    check("overlap: chunk2 start_line=61", c2.start_line == 61)
    check("overlap: chunk count = 3",      len(chunks) == 3)

    # --- coverage property: every line covered by at least one chunk ---
    covered = set()
    for ch in chunks:
        for ln in range(ch.start_line, ch.end_line + 1):
            covered.add(ln)
    check("coverage: all 100 lines covered", covered == set(range(1, 101)))

    # --- text invariant ---
    all_lines_src = src.splitlines()
    for ch in chunks:
        expected = all_lines_src[ch.start_line - 1: ch.end_line]
        check(
            f"text invariant: chunk {ch.index} text matches source lines",
            ch.text.splitlines() == expected,
        )

    # --- edge case: empty source -> [] ---
    check("edge: empty source returns []", chunk_text("") == [])

    # --- edge case: source shorter than chunk_lines -> exactly one chunk ---
    short_src = "a\nb\nc"
    short_chunks = chunk_text(short_src, chunk_lines=300, overlap_lines=30)
    check("edge: short source -> 1 chunk", len(short_chunks) == 1)
    check("edge: short source chunk covers 1..3", short_chunks[0].start_line == 1 and short_chunks[0].end_line == 3)

    # --- edge case: final chunk shorter than chunk_lines -> ends on last line ---
    src2 = "\n".join(f"x{i}" for i in range(1, 56))  # 55 lines, step=30
    chunks2 = chunk_text(src2, chunk_lines=40, overlap_lines=10)
    last = chunks2[-1]
    check("edge: final chunk ends on last line (55)", last.end_line == 55)

    # --- edge case: length exact multiple of step -> no empty trailing chunk ---
    # 60 lines, chunk_lines=40, overlap=10, step=30 -> starts: 1, 31, 61 (61>60 -> stop at 2 chunks)
    # Actually: start=0->end=40, start=30->end=60 (exact), start=60->60==total -> break
    src3 = "\n".join(f"z{i}" for i in range(1, 61))  # 60 lines
    chunks3 = chunk_text(src3, chunk_lines=40, overlap_lines=10)
    check("edge: exact-multiple -> last chunk end_line=60", chunks3[-1].end_line == 60)
    check("edge: exact-multiple -> no empty trailing chunk (all non-empty)",
          all(ch.end_line >= ch.start_line for ch in chunks3))

    # --- trailing newline does not create extra line ---
    src_trail = "a\nb\nc\n"
    tc = chunk_text(src_trail, chunk_lines=10, overlap_lines=2)
    check("edge: trailing newline -> same as without (3 lines)", tc[0].end_line == 3)

    # --- argument guards ---
    check("guard: chunk_lines=0 raises",         raised(lambda: chunk_text("x", chunk_lines=0)))
    check("guard: overlap >= chunk_lines raises", raised(lambda: chunk_text("x", chunk_lines=5, overlap_lines=5)))
    check("guard: negative overlap raises",       raised(lambda: chunk_text("x", chunk_lines=5, overlap_lines=-1)))

    print()
    if failures:
        print(f"{failures} check(s) FAILED.")
        sys.exit(1)
    else:
        print("All checks passed.")
        sys.exit(0)
