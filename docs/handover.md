# Handing the website over

The IGLC is not a legal entity, so the accounts behind iglc.net are held by a person, normally
the General Secretary or the web master they appoint. This page lists them and how each one
moves to the next person. Keep it up to date.

## What there is

| What | Where | Held by | Notes |
|---|---|---|---|
| Web app, database, file storage | Azure subscription (resource group of `iglcstorage`) | Frode Drevland | about 300 NOK/month |
| Code, deployment | GitHub repository `new-iglc-net` | Frode Drevland | deploys on every push to `main` |
| Domain iglc.net | registrar: *fill in* | *fill in* | renewal date: *fill in* |
| DNS | *fill in* | *fill in* | |
| DOIs (prefix 10.24928) | Crossref account | *fill in* | |
| Mailing list | Sender.net | *fill in* | |
| Off-site database copies | Unraid server, `appdata/iglc/backups` | Frode Drevland | weekly, see deploy-azure.md step 8 |

## Always have a second person

- **Azure:** portal → Subscriptions → the subscription → Access control (IAM) → Add role
  assignment → **Owner** → the second person's Microsoft account. They can then run and repair
  everything, but the bill still goes to the account holder.
- **GitHub:** repository → Settings → Collaborators → add them with the **Admin** role.
  Better: move the repository to a free GitHub organisation (for example `iglc`) with two
  owners; then it does not belong to a person at all. If you do, update the image name in
  deploy-azure.md step 5 and the registry token.

## Moving to a new person

1. **Azure billing:** portal → Cost Management + Billing → Subscriptions → the subscription →
   **Transfer billing ownership** → the new person's email. They accept and add their card; the
   resources stay where they are and the site keeps running. (Pay-as-you-go subscriptions; see
   Microsoft's "Transfer billing ownership of an Azure subscription".)
2. **GitHub:** repository → Settings → **Transfer ownership** (or add them as organisation
   owner). Then create a new registry token under their account (deploy-azure.md step 5).
3. **Domain and DNS:** transfer at the registrar, or add them as a contact.
4. **Crossref and Sender.net:** add them as users and remove yourself.
5. **The site itself:** make them a superuser (Manage → Settings → Users) and remove your own account's
   superuser status afterwards.
6. **Secrets** (database password, Django secret key) live only in the App Service settings.
   A new holder can read them there. After a handover, it is good practice to set a new
   database password (`az postgres flexible-server update --admin-password`) and update
   `DATABASE_URL`.

## If the site has to move away from Azure

Everything runs in one container (`Dockerfile`) with a PostgreSQL database, so any host that
runs Docker works; `docker-compose.prod.yml` is a complete setup for one server. Move the
database with `pg_dump`/`pg_restore` and keep using the storage account for files, or copy the
containers elsewhere and change `LEGACY_CONTENT_URL`, the paper file URLs and the media storage
settings.
