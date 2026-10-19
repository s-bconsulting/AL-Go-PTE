# Changelog

All notable changes to the `bc-xlf-translator` skill will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-10-19 - @SBAurelien

### Added

- `versions` subcommand and step 0: the most recent installed copy of the skill (repo, personal or organisation) is the one followed
- Standard glossary `glossary.std.<lang>.md` generated from the translation files of the `.alpackages` dependencies (Base Application, other Microsoft apps, other publishers), with the source versions in its header
- `std-status` (checked at every run, regenerated when missing or on a new major version), `std-build`, `std-lookup` and `std-conflicts` subcommands; the dependencies' xlf files are read in memory from the `.app` packages, nothing is extracted to disk
- Conflicts between the standard and the business vocabulary are asked to the user, the business wording being recommended; accepted gaps are kept in the "Écarts avec le standard" section of the extension glossary
- Every target language found in `Translations` is processed, each with its own glossaries
- Three-letter Windows language codes recognised in AL comments for the other languages (`DEU=`, `NLB=`…)

## [1.2.0] - 2026-09-30 - @SBAurelien

### Added

- Extension glossary `Translations/glossary.<lang>.md`, read first and updated after each run
- `terms` subcommand listing the most frequent Caption translations to bootstrap a glossary
- Check that the same source gets the same translation within a batch

### Changed

- Script and glossary paths independent of the install location (personal skills folder, repo, AL-Go app subfolder)

## [1.1.0] - 2026-09-30 - @SBAurelien

### Added

- Review of every AL comment (spelling, grammar, meaning, vocabulary) before it is applied
- Doubtful or wrong comments are moved to the list to verify, with a corrected proposal and the reason
- `apply --report` option: markdown table (Source | Target) of the translated units, shown to the user at the end

## [1.0.0] - 2026-09-30 - @SBAurelien

### Added

- Initial skill release
- `scripts/xlf_translate.py` with `extract`, `lookup` and `apply` subcommands
- Translation from the AL Comment (Developer note: `fr-FR=`, `FRA=` formats)
- Suggested translations for units without comment, written only after user validation
- `state="translated"` set on every written target
