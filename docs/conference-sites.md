# Conference websites

Each IGLC conference gets a small website on the IGLC platform, at `conference.iglc.net/<year>/`
(on the preview: `conference.iglc.drevland.net`). The current conference also answers at
`conference.iglc.net/`, so that address can be printed on calls for papers year after year; short
addresses such as `conference.iglc.net/call-for-papers/` go to the current conference's page. The
year address is the canonical one, so the site stays where it is once the next conference takes over.

Code: `apps/conferences`. The pages are Wagtail pages in their own Wagtail Site, whose host name
follows `SITE_URL` ("conference." + the host without "www."; setting `CONFERENCE_HOST` to override).
`ConferenceHostMiddleware` gives that host its own URLs (`config/conference_urls.py`): the pages,
robots.txt, a sitemap and uploaded files. The back office stays on the main site at `/manage/`.

## Setting up a conference's website (IGLC)

1. The conference must be in the archive (Archive → Conferences) with its number, city, country and
   dates. It stays hidden from the proceedings until its papers are published.
2. Pages → IGLC conferences → Add child page → Conference home page. Choose the conference; the
   address is its year. Saving creates:
   - the standard pages below it, as drafts: call for papers, important dates, programme, keynotes,
     committees, accepted papers, venue and travel, registration, sponsors (delete what is not needed).
     The list, its order and each page's starting text are edited under Settings → Conference
     standard pages (superusers); changes apply to sites created afterwards;
   - the group **IGLC nn organisers**, which may edit these pages and upload pictures and documents
     to the collection **IGLC nn**.

   From the command line instead: `python manage.py seed_conference_site 35 --current`.
3. Add the organisers' accounts to that group (Settings → Users). They log in at `/manage/`.
4. Settings tab of the home page (superusers only): **current conference** (served at the site's main
   address; marking one unmarks the others) and **frozen**.

## What the organisers do

- Edit and **publish** the pages themselves (Publish in the menu under Save draft), no IGLC approval
  needed; they can also unpublish. They cannot change the current/frozen settings,
  delete the site, or touch other conferences' pages.
- Branding tab of the home page: logo, a wide photograph, two colours and the heading font. The layout
  stays the IGLC's (responsive and accessible); a primary colour too light for white text is refused.
  Fonts are served by the site itself, not by a font service.
- Important dates are entered once, on the home page, and shown wherever a page has an
  "important dates" block. An extended deadline keeps the old date, struck through.

## From the platform

- Conference number, city and dates, and the tracks: the conference record in the archive.
- Accepted papers: the papers the IGLC has from ConfTool for the proceedings (withdrawn papers left
  out, no e-mail addresses); after publication, the published papers with links.
- The proceedings editors, on the committees page (can be switched off).

## After the conference

Mark the home page **frozen**: organisers can no longer change anything, and the site says that the
conference has taken place and links to its proceedings. The archive's conference page links to the
website ("Conference website") as long as it is published.

## The programme

Sessions, chairs, locations and papers are entered under Manage → Conference programme, by the
conference chairs and each part's editors (not the organisers, who keep the locations). The
programme page shows them with the "Programme" block. See docs/programme.md, which also has what
comes next: the registration backing of papers and program.iglc.net.
