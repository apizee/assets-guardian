# Changelog

All notable changes to **Assets Guardian** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-14

Adds the Microsoft 365 connector and lifts Assets Guardian off the local filesystem: configuration can now be read from, and reports published to, a SharePoint document library, with the audit report optionally emailed to a list of recipients. Rule severities also become fully configurable instead of being fixed in code.

### Added

- **Microsoft 365 plugin**: audits users (account state, MFA methods, sign-in activity, licenses), directory roles, groups and their members, and app registrations. Authenticates against **Microsoft Graph** with app-only OAuth2 (tenant / application ID / client secret). See its [`CREDENTIALS.md`](src/assets_guardian/plugins/microsoft365/CREDENTIALS.md) for the required Graph permissions.
- **SharePoint storage**: every entry of `paths` accepts a `remote:<instance>:<path>` prefix. Input files are downloaded to the local cache before use and re-downloaded when the SharePoint version changes, generated reports are uploaded once produced. Requires a configured `microsoft365` instance.
- **Email notifications**: the new `notification_email` key takes a list of recipients that receive the PDF audit report at the end of an `audit` run, sent through Microsoft Graph.
- **`script` command**: runs a custom Python file from `scripts/` with the fully bootstrapped application context (configuration, logging, registries and collectors already discovered).
- **Configurable log location**: the new `logging.path` key sets the directory where log files are written, as a relative or absolute path. Remote destinations are not supported.
- **Date-stamped report filenames**: writing the literal `DATE` in the filename of `paths.excel` or `paths.pdf` substitutes the current date (`YYYY_MM_DD`).
- **Multiple identifiers per employee**: `email` and `username` in `employees.json` now accept a list as well as a single value, so one employee holding several accounts is matched.
- **Access matrix guide**: a dedicated document explaining how to fill the authorization matrices, with the accepted scope columns and cell values per plugin.
- **`make security-trivy`**: runs the same Trivy image scan locally as the CI pipeline.
- **Identity naming-convention compliance rules** (`CTRL_HUMAN_*`, `CTRL_SERVICE_*`, `CTRL_GENERIC_*` in `plugins/default_rules.py`): check identity attributes (last/first/full name, username, email, job title, description, creation date, creator) against the company's identity-creation naming convention, one rule per attribute and identity type (human, non-human/service, generic). Coverage depends on what each source populates — a rule silently skips identities missing the field it checks rather than guessing (e.g. GitLab has no separate first/last name).
- **Excel workbook integrity checks**: every `sync` now locks auto-generated sheets read-only within Excel's UI (a deterrent, not encryption — "... Matrix" sheets stay editable on purpose) and stamps every sheet, including Matrix ones, with a SHA-256 checksum. The next `sync` compares it and logs a warning naming any sheet modified outside Assets Guardian since the last write — along with the file's last author and save date when available — without ever blocking the write itself.

### Changed

- **Rule severities are read from `rules_config.yml`** for every rule, including the matrix and default rules that previously hardcoded them. A missing or empty `severity` logs a warning and falls back to the rule's default instead of aborting the audit.
- **`DEFAULT-002` (inactivity) now takes tiered thresholds**: a single `inactivity_threshold_days` list, each entry pairing a number of days with the severity to raise. The rule reports the highest tier reached.
- **`author.fullname` and `author.email` are mandatory** and displayed on the PDF title page.
- **The environment check is far more thorough**: `assets-guardian check` now validates the logging path and folder, the output path parents, the cache directory, the syntax of notification emails, and that every configured integration matches an existing plugin.
- **Cache cleanup empties the whole cache directory** in production, instead of only the JSONL batches, so files pulled from SharePoint and staged artifacts are cleared too.

> ⚠️ **Upgrading from 0.1.1 requires editing `config.yml` and `rules_config.yml`:**
>
> - Rename `paths.rules_config` to **`paths.rules`**.
> - Replace `DEFAULT-002`'s three `inactivity_threshold_days_warning` / `_danger` / `_critical` keys with the single `inactivity_threshold_days` list.
> - Make sure `author.fullname` and `author.email` are set, they are now required.
> - Mirror any new key in `template.config.yml`, which the startup validation reads.

## [0.1.1] - 2026-07-05

First public, open-source release of Assets Guardian: a modular, multi-source, multi-instance Identity and Access Management (IAM) governance tool that audits identities, access rights and security compliance across an IT environment and consolidates everything into a single unified format.

### Added

- **Compliance audit engine** that collects identities and access rights from every enabled source and evaluates them against an extensible, rule-based policy.
- **Command-line interface** with `check` (config, connectivity & permissions diagnostics), `sync` (build/update the Excel inventory) and `audit` (evaluate rules & generate the PDF report) commands.
- **Reporting**:
  - Excel IAM inventory/register, with instance-specific sheet naming and filtering.
  - PDF audit reports.
- **Plugin architecture**: self-contained connectors, activated on demand via `config.yml`, with multi-instance support and no changes required to the core:
  - **GitLab** plugin: audits users, groups, projects and access rights.
  - **Dolibarr** plugin: audits users, groups and access rights.
- Project version dynamically retrieved from `pyproject.toml`.
- **Documentation & governance**: Sphinx-generated docs, a software-architecture overview and a plugin-creation guide, plus open-source governance files: `LICENSE.txt` (GPLv3), `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md` and `SECURITY.md`.

[0.2.0]: https://github.com/apizee/assets-guardian/releases/tag/v0.2.0
[0.1.1]: https://github.com/apizee/assets-guardian/releases/tag/v0.1.1
