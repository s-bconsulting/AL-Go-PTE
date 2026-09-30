#!/usr/bin/env python3
"""Translate Business Central XLIFF files from Developer comments.

Subcommands:
  extract  List pending trans-units (state not translated/final/signed-off or empty
           target). Splits them into units whose translation comes from the AL
           Comment (Developer note) and units that need a suggested translation.
  lookup   Search existing translated units for a term (terminology consistency).
  terms    List the most frequent Caption translations (to bootstrap a glossary).
  apply    Write translations from a JSON file into the XLF and set
           state="translated".

The file is edited as text (regex per trans-unit) so that formatting, attribute
order, encoding and line endings are preserved byte for byte outside the
touched <target> elements.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

DONE_STATES = {"translated", "final", "signed-off"}
UNIT_RE = re.compile(r"<trans-unit\b[^>]*>.*?</trans-unit>", re.DOTALL)
ID_RE = re.compile(r'<trans-unit\b[^>]*\bid="([^"]*)"')
SOURCE_RE = re.compile(r"<source>(.*?)</source>", re.DOTALL)
TARGET_RE = re.compile(r"<target\b([^>]*?)(?:/>|>(.*?)</target>)", re.DOTALL)
STATE_RE = re.compile(r'\bstate="([^"]*)"')
DEV_NOTE_RE = re.compile(r'<note from="Developer"[^>]*?(?:/>|>(.*?)</note>)', re.DOTALL)
GEN_NOTE_RE = re.compile(r'<note from="Xliff Generator"[^>]*?(?:/>|>(.*?)</note>)', re.DOTALL)
PLACEHOLDER_RE = re.compile(r"%\d+|#\d+#+")


def lang_aliases(lang):
    aliases = {lang}
    if lang.lower() == "fr-fr":
        aliases.add("FRA")
    return aliases


def comment_translation(note, lang):
    """Return the translation for `lang` found in an AL Comment, or None.

    Accepts "fr-FR = text", "fr-FR=text", "FRA = text", 'FRA="text"', and
    comments holding several languages separated by ';' or '|'.
    """
    if not note:
        return None
    text = html.unescape(note)
    names = "|".join(re.escape(a) for a in lang_aliases(lang))
    m = re.search(rf"(?i)(?:^|[;|]\s*)(?:{names})\s*=\s*(.*)", text, re.DOTALL)
    if not m:
        return None
    value = m.group(1)
    # Stop at the next "xx-XX=" / "XXX=" language entry, if any.
    nxt = re.search(r"\s*[;|]\s*(?:[a-zA-Z]{2}-[a-zA-Z]{2}|[A-Z]{3})\s*=", value)
    if nxt:
        value = value[: nxt.start()]
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value or None


def placeholders(text):
    return sorted(PLACEHOLDER_RE.findall(text or ""))


def check(source, target, context):
    """Return a list of warnings for a candidate translation."""
    issues = []
    if placeholders(source) != placeholders(target):
        issues.append(f"placeholders differ: source {placeholders(source)} / target {placeholders(target)}")
    if "OptionCaption" in (context or "") and source.count(",") != target.count(","):
        issues.append(f"OptionCaption option count differs: {source.count(',') + 1} vs {target.count(',') + 1}")
    if source.endswith(".") != target.endswith("."):
        issues.append("final period differs from source")
    return issues


def parse_unit(block):
    tid = ID_RE.search(block).group(1)
    src = SOURCE_RE.search(block)
    tgt = TARGET_RE.search(block)
    dev = DEV_NOTE_RE.search(block)
    gen = GEN_NOTE_RE.search(block)
    state = None
    target = ""
    if tgt:
        s = STATE_RE.search(tgt.group(1))
        state = s.group(1) if s else None
        target = html.unescape(tgt.group(2) or "")
    return {
        "id": tid,
        "source": html.unescape(src.group(1)) if src else "",
        "target": target,
        "state": state,
        "developer_note": html.unescape(dev.group(1) or "") if dev else "",
        "context": html.unescape(gen.group(1) or "") if gen else "",
        "translate": 'translate="no"' not in block.split(">", 1)[0],
    }


def read(path):
    return Path(path).read_bytes().decode("utf-8")


def write(path, text):
    Path(path).write_bytes(text.encode("utf-8"))


def cmd_extract(args):
    text = read(args.file)
    from_comment, to_suggest, mismatches = [], [], []
    for m in UNIT_RE.finditer(text):
        u = parse_unit(m.group(0))
        if not u["translate"]:
            continue
        comment = comment_translation(u["developer_note"], args.lang)
        pending = u["state"] not in DONE_STATES or not u["target"].strip()
        if pending:
            if comment:
                entry = {
                    "id": u["id"], "source": u["source"], "target": comment,
                    "previous_target": u["target"], "previous_state": u["state"],
                    "context": u["context"],
                }
                entry["warnings"] = check(u["source"], comment, u["context"])
                from_comment.append(entry)
            else:
                to_suggest.append({
                    "id": u["id"], "source": u["source"], "target": "",
                    "previous_target": u["target"], "previous_state": u["state"],
                    "developer_note": u["developer_note"], "context": u["context"],
                })
        elif args.mismatches and comment and comment != u["target"]:
            mismatches.append({"id": u["id"], "source": u["source"],
                               "target": u["target"], "comment": comment})
    result = {"file": str(args.file), "lang": args.lang,
              "from_comment": from_comment, "to_suggest": to_suggest}
    if args.mismatches:
        result["translated_but_differs_from_comment"] = mismatches
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    else:
        sys.stdout.buffer.write(out.encode("utf-8"))
    print(f"\npending from comment: {len(from_comment)} "
          f"(with warnings: {sum(1 for e in from_comment if e['warnings'])}), "
          f"to suggest: {len(to_suggest)}"
          + (f", translated but differs from comment: {len(mismatches)}" if args.mismatches else ""),
          file=sys.stderr)


def cmd_lookup(args):
    text = read(args.file)
    term = args.term.lower()
    hits = 0
    for m in UNIT_RE.finditer(text):
        u = parse_unit(m.group(0))
        if u["state"] in DONE_STATES and u["target"] and term in u["source"].lower():
            line = f"{u['source']}  =>  {u['target']}\n"
            sys.stdout.buffer.write(line.encode("utf-8"))
            hits += 1
            if hits >= args.limit:
                break
    print(f"{hits} hit(s)", file=sys.stderr)


def cmd_terms(args):
    """List the most frequent short Caption translations (glossary bootstrap)."""
    text = read(args.file)
    counts = {}
    for m in UNIT_RE.finditer(text):
        u = parse_unit(m.group(0))
        if (u["state"] in DONE_STATES and u["target"] and "Property Caption" in u["context"]
                and len(u["source"].split()) <= args.max_words):
            counts.setdefault(u["source"], {}).setdefault(u["target"], 0)
            counts[u["source"]][u["target"]] += 1
    rows = sorted(counts.items(), key=lambda kv: -sum(kv[1].values()))[: args.limit]
    for source, targets in rows:
        variants = " | ".join(f"{t} ({n})" for t, n in sorted(targets.items(), key=lambda kv: -kv[1])[:3])
        sys.stdout.buffer.write(f"{sum(targets.values())}\t{source}\t{variants}\n".encode("utf-8"))


def xml_escape(value):
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cmd_apply(args):
    data = json.loads(Path(args.translations).read_text(encoding="utf-8"))
    entries = []
    for key in ("from_comment", "to_suggest", "translations"):
        entries.extend(data.get(key, []) if isinstance(data, dict) else [])
    if isinstance(data, list):
        entries = data
    wanted = {e["id"]: e["target"] for e in entries if e.get("target", "").strip()}

    text = read(args.file)
    applied, warnings, rows = set(), [], []

    def replace(m):
        block = m.group(0)
        tid = ID_RE.search(block).group(1)
        if tid not in wanted:
            return block
        u = parse_unit(block)
        value = wanted[tid]
        for w in check(u["source"], value, u["context"]):
            warnings.append(f"{tid}: {w}")
        new_target = f'<target state="{args.state}">{xml_escape(value)}</target>'
        tgt = TARGET_RE.search(block)
        if tgt:
            block = block[: tgt.start()] + new_target + block[tgt.end():]
        else:
            src = SOURCE_RE.search(block)
            indent = re.search(r"\n([ \t]*)<source>", block)
            nl = "\r\n" if "\r\n" in block else "\n"
            pad = indent.group(1) if indent else ""
            block = block[: src.end()] + nl + pad + new_target + block[src.end():]
        applied.add(tid)
        rows.append((u["source"], value))
        return block

    new_text = UNIT_RE.sub(replace, text)
    missing = sorted(set(wanted) - applied)
    if not args.dry_run:
        write(args.file, new_text)
    if args.report:
        def cell(value):
            return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")
        lines = ["| # | Source | Target |", "|---|--------|--------|"]
        lines += [f"| {i} | {cell(s)} | {cell(t)} |" for i, (s, t) in enumerate(rows, 1)]
        Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{'would apply' if args.dry_run else 'applied'}: {len(applied)}, "
          f"ids not found: {len(missing)}, warnings: {len(warnings)}", file=sys.stderr)
    for w in warnings:
        print(f"WARNING {w}", file=sys.stderr)
    for tid in missing:
        print(f"NOT FOUND {tid}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract")
    e.add_argument("file")
    e.add_argument("--lang", default="fr-FR")
    e.add_argument("--out")
    e.add_argument("--mismatches", action="store_true",
                   help="also report translated units whose target differs from the comment")
    e.set_defaults(func=cmd_extract)

    lk = sub.add_parser("lookup")
    lk.add_argument("file")
    lk.add_argument("term")
    lk.add_argument("--limit", type=int, default=20)
    lk.set_defaults(func=cmd_lookup)

    tm = sub.add_parser("terms")
    tm.add_argument("file")
    tm.add_argument("--limit", type=int, default=250)
    tm.add_argument("--max-words", type=int, default=3)
    tm.set_defaults(func=cmd_terms)

    a = sub.add_parser("apply")
    a.add_argument("file")
    a.add_argument("translations", help="JSON produced by extract (edited) or a list of {id, target}")
    a.add_argument("--state", default="translated")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--report", help="write a markdown table (Source | Target) of the applied units")
    a.set_defaults(func=cmd_apply)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
