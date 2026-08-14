# 🔐 Access Matrix Guide

> ⚠️ **Warning:** This documentation is a work in progress. Some sections may be incomplete, inaccurate, or subject to change.

This guide explains how to fill in the **access matrices** (authorization matrices) that Assets Guardian generates as empty Excel sheets. These matrices are the reference against which the `audit` command validates the accesses actually collected on your platforms: *any access held by an employee that is not covered by the matrix raises a finding in the audit report*.

## 🧭 How matrices work

### 🔄 Lifecycle

1. **Generation**: the first `sync` run creates one matrix sheet per audited plugin instance in the Excel workbook (`paths.excel` in `config.yml`, by default `outputs/assets_guardian.xlsx`). The sheet is created **empty**: a header row with example scope columns, and one row per profile found in `employees.json`.
2. **Manual completion**: you replace the example columns with your real scopes and fill in the authorized role for each *(profile, scope)* pair. This is the manual step described in this guide.
3. **Preservation**: on every subsequent `sync`, matrix sheets are preserved **as-is** (they are copied verbatim into the regenerated workbook, never overwritten).
4. **Consumption**: the `audit` command reads the matrices back from the same Excel file and evaluates the `MATRIX-XXX` rules against the collected accesses.

> 💡 **Tip:** `paths.excel` can be `local:` or `remote:` (SharePoint, via the Microsoft 365 plugin). In the remote case, the workbook is cached locally and re-downloaded whenever the SharePoint version changes, exactly like `rules_config.yml` and `employees.json`.

### 🏷️ Sheet naming

Each matrix sheet is named after its source plugin and instance:

| Situation | Sheet name |
| :--- | :--- |
| Plugin instance with an `instance_id` | `<Source> (<instance_id>) Matrix` (e.g. `Gitlab (production) Matrix`) |
| Plugin instance without `instance_id` | `<Source> Matrix` (e.g. `Dolibarr Matrix`) |

The `audit` command locates the sheet by this exact pattern (case-insensitive, instance-specific name first, then the generic name as fallback).

> ⚠️ **Warning:** Do not rename matrix sheets. A renamed sheet is silently ignored and the audit runs with an empty matrix.

### 📐 Sheet layout

The matrix is a pivot table: **profiles as rows, scopes as columns, authorized roles in the cells**.

| Cell | Content | Rule |
| :--- | :--- | :--- |
| `A1` | Sheet title (e.g. `Gitlab Matrix`) | Ignored by the audit, but must stay non-empty. |
| `B1`, `C1`, … | **Scope** names (one column per audited resource) | Must exactly match the expected scope keys listed per plugin below. |
| `A2`, `A3`, … | **Profile** names (one row per profile) | Must exactly match the values of the `profiles` field in `employees.json` (comma-separated values are split and trimmed). |
| Other cells | The **role/permission** the profile is authorized to hold on that scope | An **empty cell means "not authorized"**. Accepted values depend on the plugin (see below). |

Generated sheets are pre-filled with the example scope columns `Group: Example1`, `Group: Example2`, `Instance` and `Project: Example`: replace them with your real scopes.

> ⚠️ **Warning:** These example columns are identical for every plugin, they are not tailored to the source. A Dolibarr or Microsoft 365 sheet is therefore created with `Instance` and `Project: Example` columns that its rules never audit. Always replace the whole header row with the scope columns documented for that plugin below.

### 🎯 Matching rules

- All lookups are **exact string matches** (case-sensitive): profile names, scope headers and role values must be spelled exactly as documented.
- Employees are identified by **email**: matrix rules resolve a user's profiles from `employees.json` through the email attached to the collected access. A user missing from `employees.json` has no profile, so none of their audited accesses can be authorized.
- `email` and `username` in `employees.json` accept **a single value or a list**. Every value listed becomes a lookup key for the same profiles, which is how one employee holding several accounts (e.g. `john.doe@company.com` and `jdoe@company.com`) is matched. `username` is only used as a **fallback**, when the entry has no `email` at all.
- When an employee has **several profiles**, an access is authorized as soon as *one* of the profiles allows it (for hierarchical GitLab roles, the most permissive profile wins).
- Rows with an empty first cell are skipped, so blank separator rows are harmless. Extra profile rows that match no employee are ignored.

> ⚠️ **Warning:** Do not leave an empty header cell between two scope columns: it shifts the column/value alignment when the matrix is read back.

### ⚙️ Enabling the matrix rules

Matrix rules only run if they are declared in `rules_config.yml` under the source's section:

```yaml
gitlab:
  <<: *default_rules
  MATRIX-001:
    description: "Unauthorized GitLab instance administrator"
  MATRIX-002:
    description: "Unauthorized GitLab group/project access"

dolibarr:
  <<: *default_rules
  MATRIX-001:
    description: "Unauthorized Dolibarr superadmin"
  MATRIX-002:
    description: "Unauthorized critical module access"

microsoft365:
  <<: *default_rules
  MATRIX-001:
    description: "Unauthorized Microsoft365 group access"
```

> ⚠️ **Warning:** `name`, `description`, and `severity` may all be overridden from the YAML. If `severity` is missing or empty, the rule logs a warning and falls back to its default value (see the per-plugin tables below).

### 🧩 Interpretation is plugin-specific

Matrix semantics are not implemented by the audit engine but by the `MATRIX-XXX` rules that each plugin registers for its own source. The engine only extracts a neutral *(profile, scope) → cell value* mapping from the sheet and hands it to those rules; everything else, which scope columns are recognized, how cell values are interpreted (hierarchical roles on GitLab, presence-based checks on Dolibarr, accepted admin values), lives in the plugin's own rule implementations. In practice:

- A shared rule ID does not mean a shared behavior: GitLab's `MATRIX-001` and Dolibarr's `MATRIX-001` are independent implementations. This is why the sheet layout and accepted values are documented **per plugin** below, and why they can differ freely from one plugin to another.
- A plugin that ships no MATRIX rules cannot audit a matrix: declaring `MATRIX-XXX` in `rules_config.yml` for such a source logs an error and the rule is skipped, the sheet, even carefully filled in, is never read.
- Supporting matrices in a new plugin therefore means implementing its own MATRIX rules; the conventions described in this guide do not transfer automatically to other sources.

## 🦊 GitLab matrix

Sheet: `Gitlab Matrix` or `Gitlab (<instance_id>) Matrix`.

### 🗂️ Scope columns

| Column header | Audited by | What it covers |
| :--- | :--- | :--- |
| `Instance` | `MATRIX-001` (default severity: **DANGER**) | Instance-wide administrator flag. |
| `Group: <group name>` | `MATRIX-002` (default severity: **DANGER**) | Membership role on the GitLab group `<group name>`. |
| `Project: <project name>` | `MATRIX-002` (default severity: **DANGER**) | Membership role on the GitLab project `<project name>`. |

`<group name>` / `<project name>` is the **display name** of the group or project as shown in GitLab (the API `name` field, not the URL path). The prefix is capitalized and followed by a colon and a single space: `Group: Backend`, `Project: Website`.

### 🔤 Accepted cell values

**`Instance` column**: authorizes the instance administrator flag:

| Value | Meaning |
| :--- | :--- |
| `Administrator` | The profile may be a GitLab instance administrator. |
| `Administrator*` | Same effect; the trailing `*` is an annotation convention (e.g. admin granted with conditions) and is treated identically by the engine. |
| *(empty or any other value)* | Not authorized: every instance administrator with this profile is flagged. |

**`Group: …` / `Project: …` columns**: the maximum role the profile may hold, using GitLab's role hierarchy:

| Value | GitLab access level |
| :--- | :--- |
| `Guest` | 10 |
| `Reporter` | 20 |
| `Developer` | 30 |
| `Maintainer` | 40 |
| `Owner` | 50 |

The comparison is hierarchical: a cell containing `Developer` authorizes `Guest`, `Reporter` and `Developer`, but a user holding `Maintainer` or `Owner` on that scope is flagged. Spelling must be exact, any other value is treated as below `Guest` and flags every membership.

### ⚖️ Evaluation semantics

- Only groups/projects that appear **as a column** in the matrix are audited: a group or project absent from the matrix is not checked at all.
- The `Instance` check applies to **all** collected instance administrators, whether or not the `Instance` column exists (no column means nobody is authorized).
- For a user with several profiles, the **highest** authorized level across their profiles is used.

### 📝 Example

| Gitlab Matrix | Instance | Group: Backend | Group: Infra | Project: Website |
| :--- | :--- | :--- | :--- | :--- |
| R&D | | Developer | | Maintainer |
| R&D / DevOps | | Maintainer | Owner | |
| Exploitation / Information technology (IT) | Administrator | | Maintainer | |
| Support | | | | Reporter |

With this matrix, a `Support` employee owning the `Website` project raises a `MATRIX-002` finding (`Reporter` max), and any instance administrator outside the IT profile raises a `MATRIX-001` finding.

## 💼 Dolibarr matrix

Sheet: `Dolibarr Matrix` or `Dolibarr (<instance_id>) Matrix`.

### 🗂️ Scope columns

| Column header | Audited by | What it covers |
| :--- | :--- | :--- |
| `Dolibarr` | `MATRIX-001` (default severity: **CRITICAL**) | The Dolibarr **superadmin** flag (`admin = 1` on the user). |
| `banque` | `MATRIX-002` (default severity: **DANGER**) | Rights on the **Bank** module. |
| `facture` | `MATRIX-002` (default severity: **DANGER**) | Rights on the **Invoicing** module. |
| `societe` | `MATRIX-002` (default severity: **DANGER**) | Rights on the **Third parties** module. |
| `user` | `MATRIX-002` (default severity: **DANGER**) | Rights on the **Users** module. |

Module column headers use the **technical Dolibarr module names in lowercase** (`banque`, `facture`, `societe`, `user`). These four modules are the ones declared critical in the plugin (`CRITICAL_MODULES`); other Dolibarr modules are not audited by matrix rules.

### 🔤 Accepted cell values

**`Dolibarr` column**: authorizes the superadmin flag:

| Value | Meaning |
| :--- | :--- |
| `Administrateur` / `Administrator` | The profile may be a Dolibarr superadmin. |
| `Administrateur*` | Same effect, `*` being the same annotation convention as for GitLab. |
| *(empty or any other value)* | Not authorized: every superadmin with this profile is flagged. |

**Critical module columns** — presence-based check: **any non-empty value** authorizes the profile to hold rights on that module; the value itself is not interpreted. By convention, write the highest permission granted (e.g. `lire`, `creer`, `modifier`, `supprimer`) so the matrix stays readable for reviewers.

### ⚖️ Evaluation semantics

- Critical modules are **always** audited: any user holding a right on `banque`, `facture`, `societe` or `user` (including sub-permissions such as `banque.modifier` or `user.self.password`) whose profiles have no entry for that module is flagged.
- One authorized profile is enough for the access to be considered legitimate.

### 📝 Example

| Dolibarr Matrix | Dolibarr | banque | facture | societe | user |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Direction | Administrateur | modifier | modifier | creer | lire |
| Administratif / Finance | | modifier | modifier | lire | |
| Commerce & Marketing / Commerce | | | creer | creer | |
| Exploitation / Information technology (IT) | Administrateur* | | | | supprimer |

## ☁️ Microsoft 365 matrix

Sheet: `Microsoft365 Matrix` or `Microsoft365 (<instance_id>) Matrix`.

### 🗂️ Scope columns

| Column header | Audited by | What it covers |
| :--- | :--- | :--- |
| `Group: <group name>` | `MATRIX-001` (default severity: **DANGER**) | Membership in the Microsoft 365 / Azure AD group `<group name>`. |

`<group name>` is the **display name** of the group as shown in Microsoft 365 / Azure AD. The prefix is capitalized and followed by a colon and a single space: `Group: Finance`.

> 💡 **Tip:** Unlike GitLab and Dolibarr, the Microsoft 365 plugin currently ships a single matrix rule (`MATRIX-001`): there is no `MATRIX-002`.

### 🔤 Accepted cell values

**`Group: …` columns** — presence-based check: **any non-empty value** authorizes the profile to be a member of that group; the value itself is not interpreted. By convention, write a short note (e.g. `oui`, `membre`) so the matrix stays readable for reviewers.

### ⚖️ Evaluation semantics

- Only groups that appear **as a column** in the matrix are audited: a group absent from the matrix is not checked at all (same behavior as GitLab groups/projects).
- One authorized profile is enough for the access to be considered legitimate.

### 📝 Example

| Microsoft365 Matrix | Group: Finance | Group: IT-Admins |
| :--- | :--- | :--- |
| Direction | oui | |
| Administratif / Finance | oui | |
| Exploitation / Information technology (IT) | | oui |

With this matrix, any member of the `IT-Admins` group whose profiles are not IT raises a `MATRIX-001` finding.

## ✅ Filling checklist

1. Run `sync` once so the empty matrix sheets are generated with your profiles pre-filled from `employees.json`.
2. Replace the example scope columns with your real scopes (exact names, see per-plugin tables above).
3. Fill in one cell per authorized *(profile, scope)* pair; leave every unauthorized combination **empty**.
4. Make sure the source's matrix rules are declared in `rules_config.yml` (`MATRIX-001` and `MATRIX-002` for GitLab and Dolibarr, `MATRIX-001` only for Microsoft 365).
5. Run `audit` and review the `MATRIX-XXX` findings: each one is either an access to revoke or a missing authorization to add to the matrix.

> 💡 **Tip:** An entirely empty matrix is a valid starting point: the first `audit` will then flag *every* superadmin/instance administrator and every right on Dolibarr critical modules, which gives you the complete list of accesses to arbitrate. (GitLab groups/projects and Microsoft 365 groups are the exception: they are only audited once their column exists in the matrix.)
>
> ⚠️ **Warning:** The matrix is read from the workbook referenced by `paths.excel` in `config.yml`. If you archive or move the Excel file, the next `audit` runs against an empty matrix and the findings become meaningless.
>
> ⚠️ **Warning:** The same silent failure happens if `paths.excel` contains the `DATE` placeholder and `audit` runs on a different day than the `sync` that produced the workbook: `audit` looks for **today's** filename, does not find it, and evaluates every matrix rule against an empty matrix. Run both commands on the same day, or drop `DATE` from `paths.excel`.
