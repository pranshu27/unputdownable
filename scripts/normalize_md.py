#!/usr/bin/env python3
"""Join hard-wrapped markdown into continuous single-line paragraphs.

Obsidian renders every single newline as a real break, so wrapped source text shatters
mid-sentence. Code fences, tables, headings, lists and frontmatter are preserved; list-item
continuations and blockquote lines are joined into their parent logical line.

Usage: python scripts/normalize_md.py <path.md> [...]
"""
import re
import sys

LIST_RE = re.compile(r'^\s*(?:[-*+]|\d+\.)\s')

def is_block_start(l):
    s = l.strip()
    if not s: return 'blank'
    if s.startswith('```'): return 'fence'
    if s.startswith('|'): return 'table'
    if s.startswith('#'): return 'heading'
    if s.startswith('>'): return 'quote'
    if set(s) <= set('-=*_') and len(s) >= 3: return 'hr'
    if LIST_RE.match(l): return 'list'
    return 'text'

def normalize(text):
    lines = text.splitlines(keepends=True)
    out, i, in_fence = [], 0, False
    if lines and lines[0].strip() == '---':            # frontmatter verbatim
        out.append(lines[0]); i = 1
        while i < len(lines):
            out.append(lines[i])
            if lines[i].strip() == '---': i += 1; break
            i += 1
    while i < len(lines):
        l = lines[i]
        if l.strip().startswith('```'):
            in_fence = not in_fence; out.append(l); i += 1; continue
        if in_fence:
            out.append(l); i += 1; continue
        kind = is_block_start(l)
        if kind in ('blank', 'heading', 'table', 'hr'):
            out.append(l); i += 1; continue
        if kind == 'quote':
            buf = l.strip()[1:].lstrip(); i += 1
            while i < len(lines) and is_block_start(lines[i]) == 'quote':
                buf += ' ' + lines[i].strip()[1:].lstrip(); i += 1
            out.append('> ' + buf + '\n'); continue
        if kind == 'list':
            indent = len(l) - len(l.lstrip())
            buf = l.rstrip('\n'); i += 1
            while i < len(lines):
                nxt = lines[i]; k = is_block_start(nxt)
                if k in ('blank', 'fence', 'table', 'heading', 'hr', 'quote') or LIST_RE.match(nxt):
                    break
                if (len(nxt) - len(nxt.lstrip())) <= indent: break
                buf += ' ' + nxt.strip(); i += 1
            out.append(buf + '\n'); continue
        buf = l.rstrip('\n'); i += 1
        while i < len(lines):
            nxt = lines[i]; k = is_block_start(nxt)
            if k in ('blank', 'fence', 'table', 'heading', 'hr', 'quote', 'list'): break
            buf += ' ' + nxt.strip(); i += 1
        out.append(buf + '\n')
    return ''.join(out)

if __name__ == '__main__':
    for a in sys.argv[1:]:
        p = __import__('pathlib').Path(a)
        before = len(p.read_text().splitlines())
        p.write_text(normalize(p.read_text()))
        after = len(p.read_text().splitlines())
        print(f'{str(p):60s} {before:4d} -> {after:4d} lines')
