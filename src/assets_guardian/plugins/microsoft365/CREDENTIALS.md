# 🔑 Credentials & Configuration

This guide explains how to configure the **Microsoft 365 plugin** in `config.yml`, how to generate the credentials Assets Guardian needs, and the minimum permissions to grant on the Microsoft Entra ID side.

The plugin connects to the **Microsoft Graph API** to collect user identities (state, MFA methods, sign-in activity, licenses), directory roles, groups and their members, and app registrations. Collection itself is **read-only**, but two optional features of Assets Guardian write through the same credentials: publishing reports to SharePoint (`remote:` paths) and sending the audit report by email.

## 📡 Connection method

| | |
| :--- | :--- |
| **Protocol** | Microsoft Graph REST API (v1.0) over HTTPS, through the official `msgraph-sdk` |
| **Endpoint** | `https://graph.microsoft.com/v1.0` |
| **Authentication** | OAuth2 **client credentials** (app-only), via `ClientSecretCredential`. No signed-in user is involved |

> 💡 **Tip:** App-only means the permissions belong to the application itself, not to a person. This is what allows Assets Guardian to run unattended in a CI pipeline or a scheduled job.

## ⚙️ `config.yml` section

Add one block per tenant you want to audit:

```yaml
microsoft365:
  main: # Arbitrary environment label
    credentials:
      tenant_id: "${M365_TENANT_ID}"
      application_id: "${M365_APPLICATION_ID}"
      client_secret: "${M365_CLIENT_SECRET}"
```

| Field | Required | Description |
| :--- | :---: | :--- |
| `credentials.tenant_id` | ✅ | Directory (tenant) ID of your Microsoft Entra ID tenant, a GUID. |
| `credentials.application_id` | ✅ | Application (client) ID of the registered app, a GUID. |
| `credentials.client_secret` | ✅ | Client secret value generated for the app. See [Generating the credentials](#️-generating-the-credentials) below. |
| `scopes` | - | List of OAuth2 scopes requested. Defaults to `["https://graph.microsoft.com/.default"]`, which is what app-only authentication expects. Leave it out unless you have a specific reason. |

> ⚠️ **Warning:** Never write the tenant ID, application ID, or secret in plain text in `config.yml`. Use the `${VAR_NAME}` syntax to reference an environment variable, it is resolved at startup (see [GETTING_STARTED.md](../../../../docs/markdown/GETTING_STARTED.md)).
>
> ⚠️ **Warning:** This section takes no `url` key. Unlike the GitLab and Dolibarr plugins, the Graph endpoint is not configurable, the SDK resolves it. Only `scopes` influences the request, and `.default` is the correct value for app-only authentication.
>
> 💡 **Tip:** You can declare several tenants under the `microsoft365:` key, each with its own credentials. The label (`main` here) becomes the instance identifier used in report sheet names and findings.

## 🔐 Environment variables

Declare the referenced variables in your `.env` file (or inject them via your shell, Docker, or CI/CD secrets):

```bash
# .env
M365_TENANT_ID=00000000-0000-0000-0000-000000000000
M365_APPLICATION_ID=11111111-1111-1111-1111-111111111111
M365_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> 💡 **Tip:** When running several tenants, embed the instance label in the variable name (`M365_MAIN_TENANT_ID`, `M365_TEST_TENANT_ID`, ...) to keep `.env` readable.

## 🛠️ Generating the credentials

**Prerequisites:** an account with the **Application Administrator**, **Cloud Application Administrator**, or **Global Administrator** role in Microsoft Entra ID. Granting admin consent (Step 4) specifically requires **Privileged Role Administrator** or **Global Administrator**.

### Step 1: Register the application

1. Go to the [Microsoft Entra admin center](https://entra.microsoft.com/) → **Identity → Applications → App registrations**.
2. Click **New registration** and give it an explicit name (e.g. `assets-guardian`).
3. Under **Supported account types**, select **Accounts in this organizational directory only**.
4. Leave **Redirect URI** empty: app-only authentication never redirects a browser.
5. Click **Register**.

On the app's **Overview** page, copy the **Directory (tenant) ID** and the **Application (client) ID** into your `.env` file.

### Step 2: Create a client secret

1. On the app, go to **Certificates & secrets → Client secrets → New client secret**.
2. Give it a description and an expiry (Microsoft caps it at 24 months).
3. Copy the **Value** immediately into your `.env` file.

> ⚠️ **Warning:** The secret **Value** is displayed only once, right after creation. Once you leave the page it can never be read again, only deleted and recreated. Do not confuse it with the *Secret ID*, which is not a credential.

### Step 3: Add the API permissions

Go to **API permissions → Add a permission → Microsoft Graph → Application permissions**, then add the permissions below.

> ⚠️ **Warning:** Choose **Application permissions**, not *Delegated permissions*. Delegated permissions act on behalf of a signed-in user and will not work for an unattended run.

Always required, the plugin fails its health check without them:

| Permission | Why Assets Guardian needs it |
| :--- | :--- |
| `User.Read.All` | Collect the user list and their attributes (account state, job title, creation and password dates) |
| `UserAuthenticationMethod.Read.All` | Read each user's registered authentication methods to determine MFA status |
| `AuditLog.Read.All` | Read `signInActivity` to detect inactive accounts |
| `RoleManagement.Read.All` | Collect directory role definitions and their assignments, used to flag privileged accounts |
| `Group.Read.All` | Collect groups |
| `GroupMember.Read.All` | Collect group memberships, used by the access matrix rules |
| `Application.Read.All` | Collect app registrations and their service principals (enabled state) |
| `Organization.Read.All` | Collect subscribed licenses (SKUs) and per-user license assignments |

Required only for specific features:

| Permission | Required when |
| :--- | :--- |
| `Sites.ReadWrite.All` | Any entry of `paths` in `config.yml` uses the `remote:` prefix, so files are read from and written to a SharePoint document library |
| `Mail.Send` | `notification_email` is configured, so the audit report is emailed at the end of a run |

> 💡 **Tip:** Assets Guardian computes this list from your own configuration at runtime. If you use neither SharePoint nor email notifications, do not grant those two, they are the only permissions in the set that allow writing.

### Step 4: Grant admin consent

Still on **API permissions**, click **Grant admin consent for \<your tenant\>** and confirm. Every permission must show **Granted** with a green check.

> ⚠️ **Warning:** Adding a permission is not enough. Without admin consent the application holds no effective permission and every Graph call is rejected. This is the single most common cause of a failing setup.

## ✅ Verifying the setup

Run the built-in health check, it validates connectivity and credentials for every configured instance:

```bash
assets-guardian check
```

The Microsoft 365 health check goes further than the other plugins: it authenticates, reads the permissions actually granted to the application, and compares them against the list its own configuration requires. When something is missing, the exact set is logged:

```text
WARNING - Missing permissions: ['AuditLog.Read.All', 'Organization.Read.All']
```

## 🧯 Troubleshooting

| Symptom | Likely cause | Fix |
| :--- | :--- | :--- |
| `Missing permissions: [...]` in the logs | The listed permissions are not granted, or admin consent was never given | Add them as **Application** permissions and grant admin consent (Steps 3 and 4) |
| `AADSTS7000215: Invalid client secret provided` | Wrong or expired secret, or the *Secret ID* was copied instead of the *Value* | Create a new client secret and copy its **Value** (Step 2) |
| `AADSTS700016: Application not found in the directory` | `application_id` does not match the registered app, or points to another tenant | Re-copy the **Application (client) ID** from the app's Overview page |
| `AADSTS90002: Tenant not found` | `tenant_id` is wrong | Re-copy the **Directory (tenant) ID** from the app's Overview page |
| Health check passes but MFA is empty for every user | `UserAuthenticationMethod.Read.All` is missing, the per-user call fails and MFA collection is skipped for all remaining users after the first failure | Add the permission and grant admin consent (Steps 3 and 4) |
| `Output path is remote but no microsoft365 integration is configured` | A `paths` entry uses `remote:` while the `microsoft365:` section is missing or commented out | Configure this plugin, or switch the path back to `local:` |
| Reports are never emailed | `notification_email` is empty, or `Mail.Send` is missing | Fill `notification_email` in `config.yml` and grant `Mail.Send` |

## 🛡️ Security recommendations

- Treat the client secret like a password: combined with the tenant and application IDs, it grants read access to your entire directory, every user, group, role assignment, and license.
- Keep the secret out of version control: `.env` is git-ignored, `config.yml` must only contain the `${...}` reference.
- Grant only the permissions your configuration actually uses. `Sites.ReadWrite.All` and `Mail.Send` are the only ones that allow writing, skip them if you use neither SharePoint paths nor email notifications.
- Secrets expire, Microsoft caps them at 24 months. Note the expiry date and rotate before it lapses, an expired secret breaks every scheduled run silently until someone reads the logs.
- Prefer a dedicated app registration for Assets Guardian over reusing an existing one, so its permissions can be reviewed and revoked independently.
- For a hardened setup, consider replacing the client secret with a **certificate credential**, which is not a shared string and cannot leak through logs or environment dumps.
