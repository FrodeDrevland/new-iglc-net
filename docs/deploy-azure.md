# Production on Azure

The production site runs as a container on **Azure App Service (Linux)** with **Azure Database
for PostgreSQL (Flexible Server)**. Uploaded images and documents go to a `media` container in
the existing `iglcstorage` storage account, next to the papers. Every push to `main` is tested
on PostgreSQL by GitHub Actions and, if the tests pass, deployed.

```
GitHub (main) --Actions: test, build--> ghcr.io image --deploy--> App Service --> PostgreSQL
                                                                     |
                                                                     +--> blob storage: papers, content, proceedings, media
```

Rough cost (smallest tiers, North Europe, 2026 list prices): App Service B1 about $13/month,
PostgreSQL B1ms about $13/month plus 32 GB storage, plus the storage account as today.

The steps below use the Azure CLI in PowerShell (`az login` first). Names in `<>` are yours to
choose; web app and database server names must be unique across Azure.

## 1. Where things go

Put everything in the storage account's resource group and region:

```powershell
$rg  = az storage account show -n iglcstorage --query resourceGroup -o tsv
$loc = az storage account show -n iglcstorage --query primaryLocation -o tsv
$app = "iglc-net"          # web app name -> iglc-net.azurewebsites.net
$db  = "iglc-net-db"       # database server name -> iglc-net-db.postgres.database.azure.com
```

Passwords and keys: use letters and digits only (they go into URLs). This makes a 40-character one:

```powershell
function New-Secret { -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 40 | % {[char]$_}) }
$dbPassword = New-Secret
$secretKey  = New-Secret
```

Keep both in your password manager. They are never committed.

## 2. Database

```powershell
az postgres flexible-server create -g $rg -n $db -l $loc `
  --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 `
  --admin-user iglcadmin --admin-password $dbPassword `
  --database-name iglc --backup-retention 35 --public-access 0.0.0.0
```

`--public-access 0.0.0.0` lets Azure services (the web app) connect. Azure keeps automatic
backups for 35 days and can restore to any point in that time. To reach the database from home
(for the data transfer and the weekly off-site copy), allow your public IP:

```powershell
$myIp = (Invoke-RestMethod https://api.ipify.org)
az postgres flexible-server firewall-rule create -g $rg -n $db --rule-name home `
  --start-ip-address $myIp --end-ip-address $myIp
```

The database URL used below:

```powershell
$dbUrl = "postgres://iglcadmin:$dbPassword@$db.postgres.database.azure.com:5432/iglc?sslmode=require"
```

## 3. Media container

```powershell
az storage container create --account-name iglcstorage -n media --public-access blob --auth-mode key
$storage = az storage account show-connection-string -n iglcstorage -g $rg -o tsv
```

## 4. Web app

```powershell
az appservice plan create -g $rg -n iglc-plan -l $loc --is-linux --sku B1
az webapp create -g $rg -p iglc-plan -n $app --container-image-name mcr.microsoft.com/appsvc/staticsite:latest
az webapp update -g $rg -n $app --https-only true
az webapp config set -g $rg -n $app --always-on true --generic-configurations '{\"healthCheckPath\": \"/healthz\"}'
```

The placeholder image is replaced by the first deployment (step 6).

Settings (environment variables for the container):

```powershell
az webapp config appsettings set -g $rg -n $app --settings `
  WEBSITES_PORT=8000 `
  DJANGO_SECRET_KEY=$secretKey `
  DATABASE_URL=$dbUrl `
  AZURE_STORAGE_CONNECTION_STRING=$storage `
  DJANGO_ALLOWED_HOSTS="$app.azurewebsites.net,www.iglc.net,iglc.net" `
  DJANGO_CSRF_TRUSTED_ORIGINS="https://$app.azurewebsites.net,https://www.iglc.net" `
  SITE_URL="https://$app.azurewebsites.net" `
  SITE_NOINDEX=1 `
  HOST_REDIRECTS="iglc.net=www.iglc.net" `
  DJANGO_ADMINS="Frode Drevland <frode.drevland@ntnu.no>"
```

`SITE_NOINDEX=1` keeps search engines away until the switch-over, when `SITE_URL` changes to
`https://www.iglc.net` (see switch-over.md).

Optional, for password-reset mails and error reports by email: `EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`. Without them, mails are only
written to the log.

## 5. Let App Service pull the image

The image is stored in GitHub Container Registry next to the repository. As the repository is
private, App Service needs a token to read it:

1. GitHub → your picture → **Settings → Developer settings → Personal access tokens → Tokens
   (classic) → Generate new token (classic)**. Scope: only `read:packages`. Expiry: as long as
   you are comfortable with (note the date: the site cannot be redeployed after it runs out).
2. Give it to App Service:

```powershell
az webapp config container set -g $rg -n $app `
  --container-registry-url https://ghcr.io `
  --container-registry-user <your GitHub user name> `
  --container-registry-password <the token>
```

## 6. Deployment from GitHub

1. Allow publishing with a publish profile, and download it:

   ```powershell
   az resource update -g $rg --name scm --namespace Microsoft.Web `
     --resource-type basicPublishingCredentialsPolicies --parent sites/$app --set properties.allow=true
   az webapp deployment list-publishing-profiles -g $rg -n $app --xml > publish-profile.xml
   ```

2. In the GitHub repository: **Settings → Secrets and variables → Actions**.
   - **Secrets** tab → New repository secret `AZURE_WEBAPP_PUBLISH_PROFILE`: paste the whole
     content of `publish-profile.xml`. Then delete the file.
   - **Variables** tab → New repository variable `AZURE_WEBAPP_NAME` = `iglc-net` (your `$app`).
3. **Actions → Test and deploy → Run workflow** (or push to `main`). The first run builds the
   image and deploys it. Watch the start-up in the log stream:

   ```powershell
   az webapp log tail -g $rg -n $app
   ```

   The container runs the migrations on start. `https://iglc-net.azurewebsites.net/healthz`
   answers `ok` when it is up.

From then on, every push to `main` that passes the tests goes live within a few minutes. Pull
requests and pushes to other branches are only tested.

## 7. Data

Copy the database and the uploaded files from the preview (on the Unraid server):

```bash
cd /mnt/user/appdata/iglc
docker exec iglc-db pg_dump -U iglc --format=custom --no-owner iglc > iglc.dump
docker run --rm -v "$PWD":/d postgres:16 pg_restore --no-owner --no-privileges --clean --if-exists \
  -d "postgres://iglcadmin:PASSWORD@iglc-net-db.postgres.database.azure.com:5432/iglc?sslmode=require" /d/iglc.dump
docker run --rm -v "$PWD/media":/media mcr.microsoft.com/azure-cli \
  az storage blob upload-batch -d media -s /media --overwrite --connection-string "CONNECTION STRING"
rm iglc.dump
```

(Allow the Unraid server's public IP in the database firewall first, as in step 2.)

Then create your login if the copied data does not have one:
`az webapp ssh -g $rg -n $app` and `python manage.py createsuperuser`.

## 8. Off-site copy of the database

`deploy/unraid/pull-production.sh` dumps the production database to the Unraid server and keeps
the last eight dumps. With `--restore` it also loads the dump into the preview, so the preview
runs on current data. Add `PROD_DATABASE_URL=...` (the `$dbUrl` above) to `.env.prod` and run it
weekly from Unraid's **User Scripts** plugin:

```bash
/mnt/user/appdata/iglc/src/deploy/unraid/pull-production.sh --restore
```

## Everyday use

- **Deploy:** push to `main`. Nothing else.
- **Logs:** `az webapp log tail -g $rg -n $app`, or Azure portal → the web app → Log stream.
- **Management commands:** `az webapp ssh -g $rg -n $app`, then for example
  `python manage.py group_authors`.
- **Restore the database** to a point in time (within 35 days): Azure portal → the database
  server → Overview → Restore. This creates a new server; point `DATABASE_URL` at it.
- **Roll back a bad deployment:** Actions → an earlier successful run → Re-run jobs, or
  `az webapp config container set -g $rg -n $app --container-image-name ghcr.io/frodedrevland/new-iglc-net:<older commit sha>`.
