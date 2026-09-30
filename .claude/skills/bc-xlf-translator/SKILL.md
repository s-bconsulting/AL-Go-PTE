---
name: bc-xlf-translator
description: >
  Translates Business Central XLIFF translation files (*.fr-FR.xlf or
  any target language) using the AL Comment attribute stored in the Developer note
  (e.g. Comment = 'fr-FR=...' or 'FRA=...'), after checking each comment for
  spelling errors and consistency with the source. Doubtful comments and units
  without a usable comment get a suggested translation, consistent with the
  existing terminology, that the user validates before it is written. Every written target gets state="translated".
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

### 0. Load the extension glossary

Check whether `glossary.<lang>.md` exists in the same folder as the xlf (e.g.
`Translations/glossary.fr-FR.md`, or `<AppFolder>/Translations/glossary.fr-FR.md`
in an AL-Go repo).

- **It exists**: read it before anything else and use it for the whole run. It
  holds the extension's style rules, business and BC terms, past validated
  decisions, and open inconsistencies ("À arbitrer"). It **overrides** the
  existing translations found with `lookup`, which are not always consistent.
- **It does not exist**: create it now, without asking, so the next run can use
  it. Run `python "<skill>/scripts/xlf_translate.py" terms "<file>"` (most frequent Caption
  translations with their variants) and write the glossary with these
  sections: Règles de style, Termes métier, Termes Business Central standard,
  Décisions validées (empty), À arbitrer. Take a term's majority translation
  only when it is clearly dominant; put terms with competing variants in
  "À arbitrer" rather than picking one silently. Tell the user the glossary
  was created, then use it for this run.

### 1. Locate the file and extract pending units

Target file: `<App>.g.<lang>.xlf` in the app's `Translations` folder (not the
`.g.xlf` source file). In an AL-Go repo, the app sits in a subfolder.
Before starting, check that it contains as many `<trans-unit` as the `.g.xlf`;
if not, tell the user to synchronise it first (XLIFF Sync / NAB "Synchronize
Translation Units") — the script does not add missing units.

Write working files to the scratchpad (or a temp folder), never in the repo:

```bash
python "<skill>/scripts/xlf_translate.py" extract "Translations/<App>.g.fr-FR.xlf" --lang fr-FR --out "<scratch>/pending.json"
```

A unit is pending when its state is not `translated`/`final`/`signed-off`
(including invalid states such as `needs-translated`) or its target is empty.
The JSON contains:

- `from_comment`: pending units whose Developer note holds a translation for the
  language (`fr-FR = x`, `fr-FR=x`, `fr-fr=x`, `FRA = x`, `FRA="x"`, several
  languages separated by `;`). `target` is pre-filled with the comment text;
  `warnings` lists placeholder / OptionCaption / final-period differences.
- `to_suggest`: pending units without a usable comment (`target` is empty). The
  `developer_note` may still hold context (e.g. `%1 is the matter name`) — it is
  not a translation, use it only to understand the text.

Add `--mismatches` to also list already-translated units whose target differs
from the comment. Report only the count; do not change them unless asked.

### 2. Review the units from the comment

Do not apply a comment blindly. Read **every** `from_comment` entry and check
the comment text against the English source:
- Spelling, grammar and agreement (e.g. "la facture peut être fusionné avec un
  autre facture" → "fusionnée avec une autre facture"), accents, typos.
- Meaning: the comment really translates the source (no copy-paste from another
  field, no missing or extra information, no English left untranslated).
- Consistency with the glossary first, then with the file's vocabulary (use
  `lookup`), and with the property type (Caption, ToolTip, Label — see step 3).
  A comment that uses a term listed in "À arbitrer" is a doubt.
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

### 3. Suggestions for units without comment

For each `to_suggest` entry, write a proposal in `target`. Rules:
- Use the glossary terms; otherwise reuse the existing vocabulary of the file.
  Check terms with:
  `python "<skill>/scripts/xlf_translate.py" lookup "<file>" "<english term>"`
  (e.g. Matter → Dossier, Prepayment → Provision, Partner → Associé).
- Keep every placeholder (`%1`, `%2`, `#1##`), HTML tags/entities and `\` line
  breaks; keep the same number of comma-separated options for `OptionCaption`.
- Use the `context` note (object, field, property) to pick the right form:
  Caption = short label with French capitalisation (only first word capitalised),
  ToolTip = "Spécifie ..." sentence, Label = message/error sentence.
- Follow BC French conventions: `N°`, `Qté`, `Date début`, no final period on
  captions.

Present everything to verify to the user **before writing anything**, in two
tables:

Comments with a doubt or an error (from step 2):

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

### 4. Apply

```bash
python "<skill>/scripts/xlf_translate.py" apply "<file>" "<scratch>/pending.json" --dry-run
python "<skill>/scripts/xlf_translate.py" apply "<file>" "<scratch>/pending.json" --report "<scratch>/translated.md"
```

`apply` writes each non-empty `target` (from `from_comment`, `to_suggest`, or a
plain list of `{"id", "target"}`), sets `state="translated"`, drops any
`state-qualifier`, and escapes `&`, `<`, `>`. Entries with an empty target are
skipped.

### 5. Verify and report

- Re-run `extract`: the remaining pending units must be only the rejected ones.
- `git diff --stat` on the xlf: only `<target>` lines should change.
- Report: number applied from comments, number of validated suggestions, units
  still pending, and the warnings.
- Show the user the table of everything that was translated, generated by
  `--report` (`| # | Source | Target |`, one row per written unit). Display it
  in full in the reply, not only the file path.

### 6. Update the glossary

Add to the glossary what the user validated in this run:
- each corrected comment or suggestion that sets a terminology choice goes to
  "Décisions validées" (date, source, retained translation, replaced wording);
- a new recurring term goes to the matching term table;
- a term the user settled leaves "À arbitrer".
Show the user the lines added to the glossary.

Suggest to the user (do not do it automatically) to add the missing `Comment`
in the AL source for the suggested units, and to fix the `Comment` of the
corrected ones, so the next generation of the `.g.xlf` carries the right
translation.
