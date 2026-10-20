---
name: bc-xlf-translator
description: >
  Translates Business Central XLIFF translation files (*.fr-FR.xlf or
  any target language) using the AL Comment attribute stored in the Developer note
  (e.g. Comment = 'fr-FR=...' or 'FRA=...'), after checking each comment for
  spelling errors and consistency with the source. Doubtful comments and units
  without a usable comment get a suggested translation, consistent with the
  existing terminology, that the user validates before it is written. Every written target gets state="translated".
  Checks first that no more recent copy of the skill is installed, handles every
  target language found, and keeps a standard glossary extracted from the
  Base Application and the other .alpackages dependencies (regenerated on each
  new major version, conflicts with the business vocabulary asked to the user).
  Use when asked to translate the XLF/XLIFF file, fill missing translations, process
  needs-translation units, or apply the AL comments to the translation file.
---

# BC XLF Translator

Fills pending `<target>` elements of a BC `.xlf` file. The source of truth is the
AL `Comment` (exported by the compiler as `<note from="Developer">`). When no
comment gives the translation, propose one and **wait for user validation**.

Script: `scripts/xlf_translate.py` in this skill's base directory (Python 3,
stdlib only); `<skill>` below stands for that base directory. It edits the file as
text, so only the touched `<target>` lines change in the diff.

## Workflow

### 0. Use the most recent copy of the skill

The skill can be installed in several places: in the repository
(`.claude/skills/bc-xlf-translator/`, copied from the templates), in the
personal folder (`~/.claude/skills/bc-xlf-translator/`) and in the organisation
skills (`~/.claude/skills/synced/<id>/bc-xlf-translator/`). The repository copy
is the local one; the personal and organisation copies are the global ones.
Before anything else, run from the repository:

```bash
python "<skill>/scripts/xlf_translate.py" versions
```

It lists each copy with the version of its `CHANGELOG.md` and marks the running
one and the most recent one.
- **The running copy is the most recent** ("running copy is the most recent"):
  go on.
- **A more recent copy exists** ("NEWER COPY"): stop following this file. Read
  the `SKILL.md` of the more recent copy and follow it for the whole run, with
  its own script (`<skill>` becomes that copy's folder). Tell the user which
  copy and version you use. If the outdated copy is the repository one, suggest
  updating it (copy of the most recent folder); do not do it without the user's
  agreement, since it changes the repository.

### 1. Find the translation files

List every target file `<App>.g.<lang>.xlf` in the app's `Translations` folder
(not the `.g.xlf` source file). In an AL-Go repo, the app sits in a subfolder.
Each language is processed on its own, one after the other, with its own
glossaries (`glossary.<lang>.md` and `glossary.std.<lang>.md`): run steps 2 to
9 for the first language, then again for the next one. Tell the user which
languages were found. A language file without a glossary is handled like any
other: its glossaries are created in steps 2 and 3.

Before starting a language, check that its file contains as many
`<trans-unit` as the `.g.xlf`; if not, tell the user to synchronise it first
(XLIFF Sync / NAB "Synchronize Translation Units") — the script does not add
missing units.

### 2. Load the extension glossary

Check whether `glossary.<lang>.md` exists in the same folder as the xlf (e.g.
`Translations/glossary.fr-FR.md`, or `<AppFolder>/Translations/glossary.fr-FR.md`
in an AL-Go repo).

- **It exists**: read it before anything else and use it for the whole run. It
  holds the extension's style rules, business and BC terms, past validated
  decisions, the accepted gaps with the standard ("Écarts avec le standard")
  and open inconsistencies ("À arbitrer"). It **overrides** the standard
  glossary and the existing translations found with `lookup`, which are not
  always consistent.
- **It does not exist**: create it now, without asking, so the next run can use
  it. Run `python "<skill>/scripts/xlf_translate.py" terms "<file>"` (most frequent Caption
  translations with their variants) and write the glossary with these
  sections: Règles de style, Termes métier, Termes Business Central standard,
  Décisions validées (empty), Écarts avec le standard (empty), À arbitrer.
  Take a term's majority translation only when it is clearly dominant; put
  terms with competing variants in "À arbitrer" rather than picking one
  silently. Tell the user the glossary was created, then use it for this run.

### 3. Check the standard glossary

`glossary.std.<lang>.md`, next to the extension glossary, holds the standard
vocabulary taken from the translation files of the dependencies found in
`.alpackages`: Base Application first, then the other Microsoft apps (System
Application, Business Foundation…) and the other publishers' apps (e.g.
Package SB, Event Manager). It is generated by the script, never edited by
hand; its header records each app and the version it was taken from. Check it
at every run:

```bash
python "<skill>/scripts/xlf_translate.py" std-status "<Translations folder>" --lang <lang>
```

The script finds `.alpackages` above the folder (`--alpackages <path>`
otherwise) and reads the manifest of each `.app` holding a `<lang>` xlf. For
each app it prints the version recorded in the glossary, the version in
`.alpackages` and a status:
- `missing`: the glossary is absent or does not cover this app yet;
- `new-major`: `.alpackages` holds a new major version (e.g. 29 → 30);
- `ok`: same major version (a minor update does not regenerate the glossary);
- `older-major (kept)` / `not in .alpackages (kept)`: nothing to do, say it.

If it ends with `update needed: yes`, regenerate the glossary, then tell the
user which apps and versions it now covers:

```bash
python "<skill>/scripts/xlf_translate.py" std-build "<Translations folder>" --lang <lang>
```

`std-build` reads each dependency's xlf in memory, straight from its `.app`
(nothing is extracted to disk), and keeps its most frequent Captions (400 for
the Base Application, 150 for each other app). To see how the standard
translates a whole sentence (e.g. a ToolTip), search the dependencies the
same way:

```bash
python "<skill>/scripts/xlf_translate.py" std-lookup "<Translations folder>" "<english term>" --lang <lang> [--app "Base Application"]
```

Then compare the two glossaries (every run: the extension glossary changes
too):

```bash
python "<skill>/scripts/xlf_translate.py" std-conflicts "<Translations>/glossary.<lang>.md" "<Translations>/glossary.std.<lang>.md"
```

It lists the terms of the extension glossary whose translation differs from
the standard, except the gaps already accepted in "Écarts avec le standard"
for the same standard wording. If there are conflicts, present the table to
the user and ask for each line which wording to keep. **The business wording
of the extension glossary is the recommended choice**; say so in the question.
Record each answer in the extension glossary:
- business wording kept: add a row to "Écarts avec le standard" (`| Anglais |
  Standard | Retenu | Date |`), so the question is not asked again until the
  standard wording changes;
- standard wording chosen: replace the term in its table and add the change
  to "Décisions validées".

### 4. Extract pending units

Write working files to the scratchpad (or a temp folder), never in the repo:

```bash
python "<skill>/scripts/xlf_translate.py" extract "Translations/<App>.g.<lang>.xlf" --lang <lang> --out "<scratch>/pending.json"
```

A unit is pending when its state is not `translated`/`final`/`signed-off`
(including invalid states such as `needs-translated`) or its target is empty.
The JSON contains:

- `from_comment`: pending units whose Developer note holds a translation for the
  language (`fr-FR = x`, `fr-FR=x`, `fr-fr=x`, `FRA = x`, `FRA="x"`, several
  languages separated by `;`; the three-letter Windows code of the other
  languages is recognised too, e.g. `DEU=` for de-DE, `NLB=` for nl-BE). `target` is pre-filled with the comment text;
  `warnings` lists placeholder / OptionCaption / final-period differences.
- `to_suggest`: pending units without a usable comment (`target` is empty). The
  `developer_note` may still hold context (e.g. `%1 is the matter name`) — it is
  not a translation, use it only to understand the text.

Add `--mismatches` to also list already-translated units whose target differs
from the comment. Report only the count; do not change them unless asked.

### 5. Review the units from the comment

Do not apply a comment blindly. Read **every** `from_comment` entry and check
the comment text against the English source:
- Spelling, grammar and agreement (e.g. "la facture peut être fusionné avec un
  autre facture" → "fusionnée avec une autre facture"), accents, typos.
- Meaning: the comment really translates the source (no copy-paste from another
  field, no missing or extra information, no English left untranslated).
- Consistency with the extension glossary first, then with the standard
  glossary, then with the file's vocabulary (use `lookup`), and with the
  property type (Caption, ToolTip, Label — see step 6). A comment that uses a
  term listed in "À arbitrer" is a doubt. A comment that follows the standard
  where the extension glossary has a business term (or the reverse, outside
  "Écarts avec le standard") is a doubt too; propose the business term.
- Consistency within the batch: the same source must get the same translation
  (check duplicates across tables before presenting the tables).
- The script `warnings`: placeholder mismatch (`%1`, `#1##`) or wrong
  OptionCaption option count would break the app at runtime; a final-period
  difference is cosmetic.

Classify each entry:
- **Correct** — nothing to report: keep it in `from_comment`, it is applied
  without asking.
- **Doubt or error** — move it to `to_suggest`, keep the original text in a
  `comment` field, put your corrected proposal in `target`, and explain the
  issue in a `reason` field. It is then validated with the other suggestions.
  When in doubt, always move it: it is better to ask than to write a mistake.

### 6. Suggestions for units without comment

For each `to_suggest` entry, write a proposal in `target`. Rules:
- Use the extension glossary terms first, then the standard glossary for the
  Business Central terms, otherwise reuse the existing vocabulary of the file.
  Check terms with:
  `python "<skill>/scripts/xlf_translate.py" lookup "<file>" "<english term>"`
  (e.g. Matter → Dossier, Prepayment → Provision, Partner → Associé), and in
  the standard with `std-lookup` (step 3).
- When the standard and the business vocabulary disagree on a term not yet
  settled in the extension glossary, do not choose silently: propose the
  business wording and give the standard one in the table, so the user decides
  (the business wording is the recommended choice).
- Keep every placeholder (`%1`, `%2`, `#1##`), HTML tags/entities and `\` line
  breaks; keep the same number of comma-separated options for `OptionCaption`.
- Use the `context` note (object, field, property) to pick the right form:
  Caption = short label with French capitalisation (only first word capitalised),
  ToolTip = "Spécifie ..." sentence, Label = message/error sentence.
- Follow BC French conventions: `N°`, `Qté`, `Date début`, no final period on
  captions.

Present everything to verify to the user **before writing anything**, in two
tables:

Comments with a doubt or an error (from step 5):

| # | Source | AL comment | Issue | Proposed translation |
|---|--------|------------|-------|----------------------|

Units without comment:

| # | Source | Context | Proposed translation |
|---|--------|---------|----------------------|

Also give the number of comment translations judged correct that will be
applied as-is. Ask the user to validate, correct, or reject each line (for a
comment, they may also keep the original text). Update `target` with the
user's answers; set `target` to `""` for rejected lines (they stay pending).
Never write a suggestion the user has not validated.

### 7. Apply

```bash
python "<skill>/scripts/xlf_translate.py" apply "<file>" "<scratch>/pending.json" --dry-run
python "<skill>/scripts/xlf_translate.py" apply "<file>" "<scratch>/pending.json" --report "<scratch>/translated.md"
```

`apply` writes each non-empty `target` (from `from_comment`, `to_suggest`, or a
plain list of `{"id", "target"}`), sets `state="translated"`, drops any
`state-qualifier`, and escapes `&`, `<`, `>`. Entries with an empty target are
skipped.

### 8. Verify and report

- Re-run `extract`: the remaining pending units must be only the rejected ones.
- `git diff --stat` on the xlf: only `<target>` lines should change.
- Report: number applied from comments, number of validated suggestions, units
  still pending, and the warnings.
- Show the user the table of everything that was translated, generated by
  `--report` (`| # | Source | Target |`, one row per written unit). Display it
  in full in the reply, not only the file path.

### 9. Update the glossary

Add to the glossary what the user validated in this run:
- each corrected comment or suggestion that sets a terminology choice goes to
  "Décisions validées" (date, source, retained translation, replaced wording);
- a new recurring term goes to the matching term table;
- a term the user settled leaves "À arbitrer";
- a business wording kept against the standard goes to "Écarts avec le
  standard" (`| Anglais | Standard | Retenu | Date |`).
Never edit `glossary.std.<lang>.md` by hand: it is rewritten by `std-build`.
Show the user the lines added to the glossary.

Suggest to the user (do not do it automatically) to add the missing `Comment`
in the AL source for the suggested units, and to fix the `Comment` of the
corrected ones, so the next generation of the `.g.xlf` carries the right
translation.
