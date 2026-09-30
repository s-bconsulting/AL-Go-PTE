# Changelog

All notable changes to the `bc-xlf-translator` skill will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
