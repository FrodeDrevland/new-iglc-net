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
"Database password: $dbPassword"
"Django secret key: $secretKey"
```

The last two lines print them: copy both into your password manager. They are never committed.
Do the rest of the steps in the same PowerShell window, which remembers them. In a new window, set
them again from the password manager (`$dbPassword = "..."`, `$secretKey = "..."`); do not run
`New-Secret` again, which makes new values.

Switch on the Azure services the site uses (once per subscription; each takes a minute or two):

```powershell
az provider register --namespace Microsoft.DBforPostgreSQL --wait
az provider register --namespace Microsoft.Web --wait
az provider register --namespace Microsoft.Communication --wait   # email, when that is set up
```

## 2. Database

```powershell
az postgres flexible-server create -g $rg -n $db -l $loc `
  --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 `
  --admin-user iglcadmin --admin-password $dbPassword `
  --backup-retention 35 --public-access 0.0.0.0
az postgres flexible-server db create -g $rg --server-name $db --name iglc
```

(Newer versions of the Azure CLI accept `--database-name` only for elastic clusters, so the
database is made with its own command.)

`--public-access 0.0.0.0` lets Azure services (the web app) connect. Azure keeps automatic
backups for 35 days and can restore to any point in that time. To reach the database from home
(for the data transfer and the weekly off-site copy), allow your public IP:

```powershell
$myIp = (Invoke-RestMethod https://api.ipify.org)
az postgres flexible-server firewall-rule create -g $rg --server-name $db --name home `
  --start-ip-address $myIp --end-ip-address $myIp
```

The server creation prints the password in its output: do not paste that output anywhere.

The database URL used below:

```powershell
$dbUrl = "postgres://iglcadmin:$dbPassword@$db.postgres.database.azure.com:5432/iglc?sslmode=require"
```

## 3. Containers for uploaded files

`media` holds the public uploads (images, documents, published paper PDFs); `production` holds
the proceedings' working files (editors' Word files and PDFs, corrections, the licensed fonts)
and must never be public.

```powershell
az storage container create --account-name iglcstorage -n media --public-access blob --auth-mode key
az storage container create --account-name iglcstorage -n production --public-access off --auth-mode key
$storage = az storage account show-connection-string -n iglcstorage -g $rg -o tsv
```

The running heads on published papers need Times New Roman (licensed, not in the repository).
Upload `times.ttf`, `timesi.ttf` and `timesbd.ttf` from `C:\Windows\Fonts` into `fonts/` in the
private container:

```powershell
foreach ($f in "times.ttf","timesi.ttf","timesbd.ttf") {
  az storage blob upload --account-name iglcstorage -c production -n "fonts/$f" -f "C:\Windows\Fonts\$f" --auth-mode key --overwrite
}
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

Email is set up in section 4a.

## 4a. Email: Azure Communication Services

The site sends password resets, error reports (to `DJANGO_ADMINS`) and, from 2027, the authors'
"check your details" links and reminders and the notices to the editors when authors propose
corrections. It sends through **Azure Communication Services Email** with iglc.net as a verified
domain, and signs in with the web app's **managed identity**: there is no password or key to
store, and nothing that expires. The code is `apps/core/mail.py`. Set up in September 2026.

Sender `IGLC.net <noreply@iglc.net>`. Replies go to `IGLC General Secretary <webmaster@iglc.net>`
(`EMAIL_REPLY_TO`), which Forward Email passes on to the General Secretary; the authors' mails
reply to the proceedings editors instead.

Names used below (set them again in a new window, with `$rg` and `$app`):

```powershell
$email = "iglc-email"   # Email Communication Service (holds the domain)
$acs   = "iglc-acs"     # Communication Services resource (what the site talks to)
```

### Email service and domain

```powershell
az extension add --name communication --upgrade
az communication email create --name $email -g $rg --location global --data-location Europe
az communication email domain create --email-service-name $email -g $rg --domain-name iglc.net `
  --location global --domain-management CustomerManaged --user-engmnt-tracking Disabled
az communication email domain show --email-service-name $email -g $rg --domain-name iglc.net --query verificationRecords -o json
```

Data location Europe keeps the mail data in the EU/EEA. Tracking is off (no tracking pixels).

### DNS records (Cloudflare)

The iglc.net DNS is on Cloudflare. Records for Azure must be **DNS only** (grey cloud).

| Type | Name | Content | Note |
|---|---|---|---|
| TXT | `@` | `ms-domain-verification=c294fb61-de90-4f77-83f4-07603d074f59` | Domain ownership |
| TXT | `@` | `v=spf1 include:sendersrv.com include:spf.protection.outlook.com -all` | The existing SPF record, with Azure added (never two SPF records) |
| CNAME | `selector1-azurecomm-prod-net._domainkey` | `selector1-azurecomm-prod-net._domainkey.azurecomm.net` | DKIM, DNS only |
| CNAME | `selector2-azurecomm-prod-net._domainkey` | `selector2-azurecomm-prod-net._domainkey.azurecomm.net` | DKIM, DNS only |

Leave the other mail records alone: the MX records and `forward-email=...` TXT records (Forward
Email receives mail for iglc.net and forwards webmaster@, admin@ and moderator@), and Sender.net's
`include:sendersrv.com` and `sender._domainkey` (the mailing list).

Then ask Azure to check, and look at the result:

```powershell
foreach ($t in "Domain","SPF","DKIM","DKIM2") {
  az communication email domain initiate-verification --email-service-name $email -g $rg --domain-name iglc.net --verification-type $t
}
az communication email domain show --email-service-name $email -g $rg --domain-name iglc.net --query verificationStates -o json
```

Domain and DKIM were verified within minutes. Azure refused the SPF record while it ended in
`?all` ("DnsRecordsNotMatched"): it must end in `-all`. That is safe because only Sender.net
(the mailing list) and Azure send mail as iglc.net; a new sender must be added to the record
first. The domain can only be linked (next step) once Domain and SPF are verified.

### Sender, Communication Services resource and link

```powershell
az communication email domain sender-username create --email-service-name $email -g $rg --domain-name iglc.net `
  --sender-username noreply --username noreply --display-name "IGLC.net"
az communication create --name $acs -g $rg --location global --data-location Europe
$domainId = az communication email domain show --email-service-name $email -g $rg --domain-name iglc.net --query id -o tsv
az communication update --name $acs -g $rg --linked-domains $domainId -o none
```

### The web app's identity and settings

```powershell
$principalId = az webapp identity assign -g $rg -n $app --query principalId -o tsv
$acsId = az communication show --name $acs -g $rg --query id -o tsv
az role assignment create --assignee-object-id $principalId --assignee-principal-type ServicePrincipal `
  --role "Communication and Email Service Owner" --scope $acsId -o none
$acsHost = az communication show --name $acs -g $rg --query hostName -o tsv
az webapp config appsettings set -g $rg -n $app -o none --settings "AZURE_EMAIL_ENDPOINT=https://$acsHost" `
  "DEFAULT_FROM_EMAIL=IGLC.net <noreply@iglc.net>" "EMAIL_REPLY_TO=IGLC General Secretary <webmaster@iglc.net>"
```

Without `AZURE_EMAIL_ENDPOINT` (and without `EMAIL_HOST`, for an SMTP server elsewhere), mails
are only written to the log.

### Test

Log out, choose **Forgotten password?** on the back-office login page and ask for a reset to an
address you can read (a Gmail address shows the most). The mail should come from
`IGLC.net <noreply@iglc.net>` with Reply-To `webmaster@iglc.net`. In the message source ("Show
original" in Gmail), check `spf=pass`, `dkim=pass` and `dmarc=pass`. If nothing arrives, the log
stream (`az webapp log tail -g $rg -n $app`) shows the error from Azure.

### Notes

- **The preview never gets these settings.** Its database is a copy of production with the
  authors' addresses, so it must not send real mail: it writes mails to its log
  (`docker logs iglc-web`).
- **Sending quota.** A new custom domain has a low sending quota (a few dozen mails a minute and
  about a hundred an hour). Mails over the quota fail with "429" and are reported as not sent; the
  metadata-check pages send in batches, so the rest can be sent later. Before the 2027 check
  links go out, ask for a higher quota (Azure portal → Help + support → a quota request for
  Communication Services Email).
- **DMARC.** `_dmarc.iglc.net` is `v=DMARC1; p=none;`. The site's mail passes DMARC through DKIM.
- **Delete lock.** The resource group has a `CanNotDelete` lock (`iglcstorag-xrpMigration-lock`),
  which protects the storage account with the papers. Nothing in the group can be deleted,
  role assignments included, until the lock is lifted; creating and changing things works. A
  role assignment left from an abandoned SMTP attempt (shown as "Identity not found" on the
  Communication Services resource) grants nothing and was left in place.

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
docker run --rm -v "$PWD/private":/private mcr.microsoft.com/azure-cli \
  az storage blob upload-batch -d production -s /private --overwrite --connection-string "CONNECTION STRING"
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

## Crossref (DOI registration)

Deposits are made and sent on a production's publish page (publishers only). Settings:

    CROSSREF_LOGIN=<Crossref user, or email/role>
    CROSSREF_PASSWORD=<password>
    CROSSREF_DEPOSITOR_EMAIL=<address Crossref sends results to>
    CROSSREF_TEST=false          # only on the live site; everywhere else deposits go to the test system
    CROSSREF_SITE_URL=https://www.iglc.net   # the address DOIs point to (the default)

Try it first with the test system (test.crossref.org needs its own test account, asked from
Crossref support). The preview must never send to the live system: DOIs would point to the
address in CROSSREF_SITE_URL, and a wrong deposit changes the published record.

## Everyday use

- **Deploy:** push to `main`. Nothing else.
- **Logs:** `az webapp log tail -g $rg -n $app`, or Azure portal → the web app → Log stream.
- **Management commands:** `az webapp ssh -g $rg -n $app`, then for example
  `python manage.py group_authors`.
- **Restore the database** to a point in time (within 35 days): Azure portal → the database
  server → Overview → Restore. This creates a new server; point `DATABASE_URL` at it.
- **Roll back a bad deployment:** Actions → an earlier successful run → Re-run jobs, or
  `az webapp config container set -g $rg -n $app --container-image-name ghcr.io/frodedrevland/new-iglc-net:<older commit sha>`.
