# 🛡️ Assets Guardian

**One place to audit every identity and access right in your IT environment.**

![Banner](docs/_images/ag_banner.png)
![Version](https://img.shields.io/badge/version-0.2.0-blue?style=for-the-badge&logo=semver&logoColor=white)
[![License: GPLv3](https://img.shields.io/badge/license-GPLv3-blue?style=for-the-badge&logo=gnu&logoColor=white)](https://github.com/apizee/assets-guardian/blob/main/LICENSE.txt)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Documentation](https://img.shields.io/badge/docs-Sphinx-blue?style=for-the-badge&logo=sphinx&logoColor=white)](https://apizee.github.io/assets-guardian/)

Assets Guardian is a modular, multi-source, multi-instance Identity and Access Management (IAM) governance tool. It audits identities, access rights, and security compliance across every solution in your IT environment, all from one place, with data consolidated into a single unified format regardless of the source.

- **Modular Architecture**: Add, remove, or create your own custom plugins without ever modifying the core codebase.
- **Comprehensive Reporting**: Automatically generates a detailed Excel IAM inventory/register and PDF audit reports.
- **Rule-Based Engine**: Extensible compliance and rule engine for evaluating access policies.
- **Local or SharePoint Storage**: Read configuration from, and publish reports to, a SharePoint document library instead of the local filesystem.
- **Email Notifications**: Send the audit report to a list of recipients at the end of a run.

## 🔌 Available Plugins

Each plugin is self-contained and only activated when explicitly declared in `config.yml`. Every plugin supports **multiple instances** of the same platform.

| Plugin | Status | Authentication | Audited data |
| :---: | :---: | :---: | :---: |
| **GitLab** | ✅ Available | Personal Access Token (Bearer) | Users, groups, projects & access rights |
| **Dolibarr** | ✅ Available | API key (`DOLAPIKEY`) | Users, groups & access rights |
| **Microsoft 365** | ✅ Available | Microsoft Graph, app-only OAuth2 (tenant / application ID / secret) | Users (MFA, sign-in activity), groups, directory roles, app registrations & licenses |

> 💡 **Tip:** Your platform isn't listed? Adding a connector never touches the core engine, see the [Plugin Development Guide](docs/markdown/PLUGIN.md).

## 🚀 Quick Start

The fastest way to **use** Assets Guardian is to install it once as a global command, then run it from any audit folder, no `uv run` prefix, no virtual environment to activate. This mode targets operators, auditors, and IT teams who *consume* the tool.

Prerequisites:

- [**Python 3.13+**](https://www.python.org/downloads/): runtime
- [**uv**](https://github.com/astral-sh/uv): builds & installs the command
- [**make**](https://www.gnu.org/software/make/): runs the install shortcuts

### 1. Install the command

Install the `assets-guardian` command into an isolated environment on your `PATH`:

```bash
git clone git@github.com:apizee/assets-guardian.git
cd assets-guardian/
make install
```

Verify it from anywhere:

```bash
assets-guardian --version
```

> 💡 **Tip:** If your shell can't find the command, run `uv tool update-shell` and restart your terminal.

### 2. Prepare an audit folder

The installed command resolves every file **relative to the directory you launch it from**. Create a dedicated folder for your audit and drop your configuration into it:

```text
my-iam-audit/
├── config/         # config.yml, template.config.yml, rules_config.yml, employees.json, excel/pdf styling
├── .env            # plugin credentials (optional, depends on the plugins you enable)
├── logs/           # rotating log files (auto-created on first run)
└── outputs/        # generated Excel & PDF reports (auto-created on first run)
```

> ⚠️ **Warning:** Keep `template.config.yml` next to `config.yml`. It is not a backup: Assets Guardian validates your configuration against it at startup, and the run fails without it.
>
> 💡 **Tip:** The quickest way to bootstrap it is to copy the repository's `config/` directory, rename each `template.*` file (drop the `template.` prefix), and copy `.env.template` to `.env`. See [Getting Started](docs/markdown/GETTING_STARTED.md) for the full configuration reference.

### 3. Run it

From inside your working directory, call the commands directly:

```bash
cd my-iam-audit
assets-guardian --help          # show all available flags and commands
assets-guardian check           # diagnostic of config, connectivity & permissions
assets-guardian sync            # build / update the Excel IAM inventory
assets-guardian audit           # evaluate the rules & generate the PDF report
assets-guardian script <name>   # run a custom power-user script from scripts/ (advanced)
```

> 💡 **Tip:** Upgrade later with `make upgrade`, and remove the command entirely with `make uninstall`.

## 📜 License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**. See the [LICENSE.txt](LICENSE.txt) file for the full text.
