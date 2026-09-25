# Switch-over checklist: old iglc.net to the new site

The new site runs on Azure App Service (docs/deploy-azure.md) at `iglc-net.azurewebsites.net`
before this starts. Tick each item as it is done.

## A week before

- [ ] The new site works at `https://iglc-net.azurewebsites.net`, with the production data (deploy-azure.md step 7).
- [ ] The last run of **Actions → Test and deploy** is green.
- [ ] Check every old URL against it:
      `python tools/url_inventory.py check inventory/crawl.csv inventory/crossref.csv --base https://iglc-net.azurewebsites.net --workers 8`
      Only the 9 links that were already broken on the old site may fail.
- [ ] Look through the main pages as a visitor and as an editor (CMS, Manage).
- [ ] Find out where the DNS for iglc.net is managed, and that you can log in there.
- [ ] Lower the TTL of the `www` and `@` records to 5 minutes (so the change takes effect quickly).
- [ ] Decide the switch-over day and freeze changes on the old site from then (no new papers or
      page edits there; anything changed there after the data copy must be redone in the new admin).

## On the day

1. **Data.** If the preview has changed since the copy, copy it again (deploy-azure.md step 7).
2. **Settings for the real address:**

   ```powershell
   az webapp config appsettings set -g $rg -n $app --settings SITE_URL=https://www.iglc.net
   az webapp config appsettings delete -g $rg -n $app --setting-names SITE_NOINDEX
   ```

3. **Move the host names from the old app to the new one.** A host name can only be bound to
   one app, so remove it from the old site's App Service first (portal → old web app → Custom
   domains → delete `www.iglc.net` and `iglc.net`). The old site is unreachable from here
   until DNS points to the new one: a few minutes.
4. **DNS** (at the DNS provider):
   - `www` → CNAME `iglc-net.azurewebsites.net`
   - `@` (iglc.net) → A record to the new app's IP address (portal → new web app → Custom domains shows it)
   - The TXT records `asuid.www` and `asuid` with the new app's **Custom Domain Verification ID** (same page).
   - `conference` → CNAME `iglc-net.azurewebsites.net`, and TXT `asuid.conference` (the conference sites).
   - `program` → CNAME `iglc-net.azurewebsites.net`, and TXT `asuid.program` (the programme at the venue).
5. **Add the host names and free certificates** to the new app (portal → Custom domains →
   Add custom domain, App Service managed certificate), first `www.iglc.net`, then `iglc.net`,
   then `conference.iglc.net` and `program.iglc.net`. `iglc.net` redirects to `www.iglc.net` by itself (setting `HOST_REDIRECTS`);
   the conference sites' host name follows `SITE_URL` (no setting needed).
6. **Check:**
   - [ ] `https://www.iglc.net` and `https://iglc.net` open the new site, with a valid certificate.
   - [ ] `https://conference.iglc.net` opens the current conference's website.
   - [ ] `https://program.iglc.net` opens the current conference's programme (once it is published).
   - [ ] A DOI resolves to the paper page, e.g. https://doi.org/10.24928/2022/0123
   - [ ] An old URL redirects, e.g. https://www.iglc.net/Papers/Details/1000
   - [ ] https://www.iglc.net/robots.txt no longer says `Disallow: /`
   - [ ] Run the URL check again with `--base https://www.iglc.net`.
7. **Stop** (do not delete) the old web app.

## The weeks after

- [ ] Google Search Console: add the site (DNS TXT verification) and submit https://www.iglc.net/sitemap.xml.
- [ ] After a week without problems: turn on HSTS,
      `az webapp config appsettings set -g $rg -n $app --settings DJANGO_HSTS_SECONDS=31536000`.
- [ ] Crossref: update the resource URLs of all DOIs from `http://` to `https://` (a bulk
      resource-only deposit; not urgent, the old URLs redirect).
- [ ] Set the DNS TTL back to an hour or more.
- [ ] After a month: delete the old web app, its App Service plan and its SQL database. Keep
      the storage account: the papers live there.
- [ ] Update docs/handover.md with anything learnt.
