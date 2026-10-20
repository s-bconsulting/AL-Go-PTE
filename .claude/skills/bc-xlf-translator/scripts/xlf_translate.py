#!/usr/bin/env python3
"""Translate Business Central XLIFF files from Developer comments.

Subcommands:
  versions       List the copies of this skill (repo, personal, organisation) with
                 their CHANGELOG version and tell which one is the most recent.
  std-status     Compare the standard glossary (glossary.std.<lang>.md) with the
                 translation files of the dependencies found in .alpackages.
  std-build      Read those translation files and (re)write the standard glossary.
  std-lookup     Search the dependencies' translation files for a term.
  std-conflicts  List the terms whose translation in the extension glossary differs
                 from the standard glossary.
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
import datetime
import html
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote

DONE_STATES = {"translated", "final", "signed-off"}
UNIT_RE = re.compile(r"<trans-unit\b[^>]*>.*?</trans-unit>", re.DOTALL)
ID_RE = re.compile(r'<trans-unit\b[^>]*\bid="([^"]*)"')
SOURCE_RE = re.compile(r"<source>(.*?)</source>", re.DOTALL)
TARGET_RE = re.compile(r"<target\b([^>]*?)(?:/>|>(.*?)</target>)", re.DOTALL)
STATE_RE = re.compile(r'\bstate="([^"]*)"')
DEV_NOTE_RE = re.compile(r'<note from="Developer"[^>]*?(?:/>|>(.*?)</note>)', re.DOTALL)
GEN_NOTE_RE = re.compile(r'<note from="Xliff Generator"[^>]*?(?:/>|>(.*?)</note>)', re.DOTALL)
PLACEHOLDER_RE = re.compile(r"%\d+|#\d+#+")
CAPTION_ID = "Property 2879900210"
SKILL_NAME = "bc-xlf-translator"
VERSION_RE = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\]", re.MULTILINE)
SOURCES_RE = re.compile(r"<!-- bc-xlf-translator:std-sources\s*(.*?)-->", re.DOTALL)
# Three-letter Windows language codes used in older AL comments (FRA=...).
LANG_CODES = {
    "fr-fr": "FRA", "fr-be": "FRB", "fr-ch": "FRS", "fr-ca": "FRC",
    "de-de": "DEU", "de-at": "DEA", "de-ch": "DES", "nl-nl": "NLD", "nl-be": "NLB",
    "en-gb": "ENG", "es-es": "ESP", "it-it": "ITA", "pt-pt": "PTG", "da-dk": "DAN",
    "sv-se": "SVE", "nb-no": "NOR", "fi-fi": "FIN", "cs-cz": "CSY", "pl-pl": "PLK",
}


def lang_aliases(lang):
    aliases = {lang}
    if lang.lower() in LANG_CODES:
        aliases.add(LANG_CODES[lang.lower()])
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


# --- Skill copies -----------------------------------------------------------

def skill_version(folder):
    log = Path(folder) / "CHANGELOG.md"
    if not log.is_file():
        return None
    m = VERSION_RE.search(log.read_text(encoding="utf-8"))
    return tuple(int(x) for x in m.groups()) if m else None


def cmd_versions(args):
    """List the copies of the skill and point to the most recent one."""
    skills = Path.home() / ".claude" / "skills"
    found = []
    start = Path(args.repo).resolve()
    for folder in [start, *start.parents]:
        copy = folder / ".claude" / "skills" / SKILL_NAME
        if copy.is_dir():
            found.append(("repo", copy))
    found.append(("personal", skills / SKILL_NAME))
    found += [("organisation", c) for c in sorted((skills / "synced").glob(f"*/{SKILL_NAME}"))]
    running = Path(__file__).resolve().parent.parent
    found.append(("running", running))
    copies, seen = [], set()
    for kind, path in found:
        path = path.resolve()
        if not path.is_dir() or path in seen:
            continue
        seen.add(path)
        if path == (skills / SKILL_NAME).resolve():
            kind = "personal"
        copies.append((kind, skill_version(path) or (0, 0, 0), path))
    newest = max(copies, key=lambda c: c[1])
    running_version = skill_version(running) or (0, 0, 0)
    for kind, version, path in copies:
        flags = (" [running]" if path == running else "") + (" [newest]" if version == newest[1] else "")
        print(f"{kind}\t{'.'.join(map(str, version))}\t{path}{flags}")
    if newest[1] > running_version:
        print(f"NEWER COPY: {newest[0]} {'.'.join(map(str, newest[1]))} at {newest[2]} "
              f"(running {'.'.join(map(str, running_version))}). Use that copy.")
    else:
        print("running copy is the most recent")


# --- Dependencies (.alpackages) ---------------------------------------------

def vtuple(version):
    return tuple(int(x) for x in re.findall(r"\d+", version or "0"))


def open_app(path):
    """Open the zip held in a .app package (NAVX header followed by a zip)."""
    data = Path(path).read_bytes()
    start = data.find(b"PK\x03\x04")
    if start < 0:
        return None
    try:
        return zipfile.ZipFile(io.BytesIO(data[start:]))
    except zipfile.BadZipFile:
        return None


def app_info(zf):
    manifest = zf.read("NavxManifest.xml").decode("utf-8-sig", "replace")
    tag = re.search(r"<App\b[^>]*>", manifest).group(0)
    attrs = {k: html.unescape(v) for k, v in re.findall(r'(\w+)="([^"]*)"', tag)}
    return attrs.get("Publisher", ""), attrs.get("Name", ""), attrs.get("Version", "")


def own_app_name(xlf_dir):
    for folder in (xlf_dir.parent, xlf_dir):
        app_json = folder / "app.json"
        if app_json.is_file():
            return json.loads(app_json.read_text(encoding="utf-8-sig")).get("name")
    return None


def find_alpackages(xlf_dir, explicit):
    if explicit:
        return Path(explicit)
    for folder in [xlf_dir, *xlf_dir.parents]:
        if (folder / ".alpackages").is_dir():
            return folder / ".alpackages"
    sys.exit(f"no .alpackages folder found above {xlf_dir}; pass --alpackages")


def dependency_xlfs(alpackages, lang, own_name):
    """Most recent package of each app holding a <lang> translation file."""
    best = {}
    for package in sorted(alpackages.glob("*.app")):
        zf = open_app(package)
        if zf is None:
            continue
        try:
            publisher, name, version = app_info(zf)
        except (KeyError, AttributeError):
            continue
        if name == own_name:
            continue
        entry = next((n for n in zf.namelist()
                      if unquote(n).lower().endswith(f".{lang.lower()}.xlf")), None)
        if entry is None:
            continue
        key = (publisher, name)
        if key not in best or vtuple(version) > vtuple(best[key]["version"]):
            best[key] = {"publisher": publisher, "name": name, "version": version,
                         "package": package, "entry": entry}
    return sorted(best.values(),
                  key=lambda a: (a["publisher"] != "Microsoft", a["name"] != "Base Application", a["name"]))


def std_glossary_path(xlf_dir, lang):
    return xlf_dir / f"glossary.std.{lang}.md"


def std_sources(path):
    """Apps and versions recorded in the header of the standard glossary."""
    if not path.is_file():
        return None
    m = SOURCES_RE.search(path.read_text(encoding="utf-8"))
    sources = {}
    for line in (m.group(1).splitlines() if m else []):
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 3:
            sources[(parts[0], parts[1])] = parts[2]
    return sources


def read_dependency_xlf(app):
    """Translation file of a dependency, read in memory (nothing written to disk)."""
    return open_app(app["package"]).read(app["entry"]).decode("utf-8-sig")


def cmd_std_status(args):
    xlf_dir = Path(args.dir).resolve()
    glossary = std_glossary_path(xlf_dir, args.lang)
    sources = std_sources(glossary)
    apps = dependency_xlfs(find_alpackages(xlf_dir, args.alpackages), args.lang, own_app_name(xlf_dir))
    print(f"standard glossary: {glossary} ({'absent' if sources is None else 'present'})")
    needed = sources is None
    for app in apps:
        recorded = (sources or {}).get((app["publisher"], app["name"]))
        if recorded is None:
            status, needed = "missing", True
        elif vtuple(app["version"])[:1] > vtuple(recorded)[:1]:
            status, needed = "new-major", True
        elif vtuple(app["version"])[:1] < vtuple(recorded)[:1]:
            status = "older-major (kept)"
        else:
            status = "ok"
        line = (f"{app['publisher']} | {app['name']} | glossary {recorded or '-'} | "
                f"package {app['version']} | {status}\n")
        sys.stdout.buffer.write(line.encode("utf-8"))
    for publisher, name in sorted(set(sources or {}) - {(a["publisher"], a["name"]) for a in apps}):
        print(f"{publisher} | {name} | glossary {sources[(publisher, name)]} | not in .alpackages (kept)")
    print(f"update needed: {'yes' if needed else 'no'}")


def caption_terms(text, max_words):
    counts = {}
    for m in UNIT_RE.finditer(text):
        block = m.group(0)
        if CAPTION_ID + '"' not in block.split(">", 1)[0]:
            continue
        u = parse_unit(block)
        if (u["state"] in DONE_STATES or u["state"] is None) and u["target"].strip() \
                and len(u["source"].split()) <= max_words:
            counts.setdefault(u["source"], {}).setdefault(u["target"], 0)
            counts[u["source"]][u["target"]] += 1
    return sorted(counts.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))


def md_cell(value):
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def cmd_std_build(args):
    xlf_dir = Path(args.dir).resolve()
    apps = dependency_xlfs(find_alpackages(xlf_dir, args.alpackages), args.lang, own_app_name(xlf_dir))
    if not apps:
        sys.exit(f"no {args.lang} translation file found in the dependencies")
    sections, summary = [], []
    for app in apps:
        limit = args.limit_base if app["name"] == "Base Application" else args.limit
        rows = caption_terms(read_dependency_xlf(app), args.max_words)[:limit]
        summary.append((app, len(rows)))
        lines = [f"## {app['name']} ({app['publisher']} {app['version']})", "",
                 "| Anglais | Traduction | Occurrences | Variantes |", "|---|---|---|---|"]
        for source, targets in rows:
            ranked = sorted(targets.items(), key=lambda kv: -kv[1])
            variants = ", ".join(f"{t} ({n})" for t, n in ranked[1:4])
            lines.append(f"| {md_cell(source)} | {md_cell(ranked[0][0])} | "
                         f"{sum(targets.values())} | {md_cell(variants)} |")
        sections.append("\n".join(lines))
        line = f"{app['publisher']} | {app['name']} | {app['version']} | {len(rows)} terms\n"
        sys.stdout.buffer.write(line.encode("utf-8"))
    header = [
        f"# Glossaire standard Business Central (en-US → {args.lang})", "",
        "Fichier généré par la compétence `bc-xlf-translator` (commande `std-build`) à partir",
        "des fichiers de traduction des dépendances présentes dans `.alpackages`. Ne pas le",
        "modifier à la main : il est réécrit à chaque nouvelle version majeure d'une dépendance.",
        f"Les choix propres à l'extension vont dans `glossary.{args.lang}.md`, qui prime sur ce fichier.",
        "", f"Généré le {datetime.date.today().isoformat()}.", "",
        "<!-- bc-xlf-translator:std-sources",
        *[f"{a['publisher']} | {a['name']} | {a['version']}" for a, _ in summary],
        "-->", "",
        "| Application | Éditeur | Version | Termes |", "|---|---|---|---|",
        *[f"| {a['name']} | {a['publisher']} | {a['version']} | {n} |" for a, n in summary],
    ]
    out = std_glossary_path(xlf_dir, args.lang)
    out.write_text("\n".join(header) + "\n\n" + "\n\n".join(sections) + "\n", encoding="utf-8")
    sys.stdout.buffer.write(f"written: {out}\n".encode("utf-8"))


def cmd_std_lookup(args):
    xlf_dir = Path(args.dir).resolve()
    apps = dependency_xlfs(find_alpackages(xlf_dir, args.alpackages), args.lang, own_app_name(xlf_dir))
    if args.app:
        apps = [a for a in apps if a["name"].lower() == args.app.lower()]
    term, hits = args.term.lower(), 0
    for app in apps:
        for m in UNIT_RE.finditer(read_dependency_xlf(app)):
            u = parse_unit(m.group(0))
            if u["target"] and term in u["source"].lower():
                sys.stdout.buffer.write(f"[{app['name']}] {u['source']}  =>  {u['target']}\n".encode("utf-8"))
                hits += 1
                if hits >= args.limit:
                    print(f"{hits} hit(s)", file=sys.stderr)
                    return
    print(f"{hits} hit(s)", file=sys.stderr)


def norm(value):
    value = value.replace("\u2019", "'").replace("`", "").strip().rstrip(".")
    return re.sub(r"\s+", " ", value).lower()


def md_tables(path):
    """Yield (section title, cells) for each data row of the markdown tables."""
    section, in_table = "", False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped[3:].strip()
        if not stripped.startswith("|"):
            in_table = False
            continue
        if not in_table:
            in_table = True  # header row
            continue
        if re.fullmatch(r"\|[\s:|-]+\|?", stripped):
            continue  # separator row
        yield section, [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", stripped)[1:-1]]


def cmd_std_conflicts(args):
    glossary, std = Path(args.glossary), Path(args.std)
    standard = {}
    for section, cells in md_tables(std):
        if len(cells) >= 2 and "(" in section:
            standard.setdefault(norm(cells[0]), (cells[1], section.split(" (")[0],
                                                 cells[3] if len(cells) > 3 else ""))
    accepted, business = {}, []
    for section, cells in md_tables(glossary):
        if len(cells) < 2:
            continue
        title = section.lower()
        if title.startswith("écarts"):
            accepted[norm(cells[0])] = norm(cells[1])
        elif not title.startswith(("règles", "décisions", "à arbitrer")):
            business.append((cells[0], cells[1]))
    rows = []
    for english, chosen in business:
        hit = standard.get(norm(english))
        if not hit or norm(chosen) == norm(hit[0]):
            continue
        if accepted.get(norm(english)) == norm(hit[0]):
            continue  # gap already validated against this standard wording
        rows.append((english, chosen, f"{hit[0]} ({hit[1]})", hit[2]))
    lines = ["| # | Anglais | Glossaire métier (recommandé) | Standard | Variantes standard |",
             "|---|---|---|---|---|"]
    lines += [f"| {i} | {md_cell(e)} | {md_cell(c)} | {md_cell(s)} | {md_cell(v)} |"
              for i, (e, c, s, v) in enumerate(rows, 1)]
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))
    print(f"{len(rows)} conflict(s)", file=sys.stderr)


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

    v = sub.add_parser("versions")
    v.add_argument("--repo", default=".", help="folder inside the repository (default: current folder)")
    v.set_defaults(func=cmd_versions)

    ss = sub.add_parser("std-status")
    ss.add_argument("dir", help="folder holding the xlf files (Translations)")
    ss.add_argument("--lang", default="fr-FR")
    ss.add_argument("--alpackages")
    ss.set_defaults(func=cmd_std_status)

    sb = sub.add_parser("std-build")
    sb.add_argument("dir", help="folder holding the xlf files (Translations)")
    sb.add_argument("--lang", default="fr-FR")
    sb.add_argument("--alpackages")
    sb.add_argument("--limit-base", type=int, default=400, help="terms kept for the Base Application")
    sb.add_argument("--limit", type=int, default=150, help="terms kept for each other dependency")
    sb.add_argument("--max-words", type=int, default=3)
    sb.set_defaults(func=cmd_std_build)

    sl = sub.add_parser("std-lookup")
    sl.add_argument("dir", help="folder holding the xlf files (Translations)")
    sl.add_argument("term")
    sl.add_argument("--lang", default="fr-FR")
    sl.add_argument("--alpackages")
    sl.add_argument("--app", help="search only this dependency (e.g. \"Base Application\")")
    sl.add_argument("--limit", type=int, default=20)
    sl.set_defaults(func=cmd_std_lookup)

    sc = sub.add_parser("std-conflicts")
    sc.add_argument("glossary", help="extension glossary (glossary.<lang>.md)")
    sc.add_argument("std", help="standard glossary (glossary.std.<lang>.md)")
    sc.set_defaults(func=cmd_std_conflicts)

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
