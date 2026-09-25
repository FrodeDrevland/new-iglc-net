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

## The back office: Conferences

Everything about a conference is under **Conferences** in the back office menu:

- **All conferences**: the list, with the dates, whether the conference is upcoming or past, the
  state of its website, programme and proceedings, and whether it is in the archive. Clicking a
  conference opens its **dashboard**.
- **Programmes** and **Proceedings production**: the programme and the proceedings of each conference
  (docs/programme.md, docs/production-process.md).
- **Website standard pages**: the pages every new conference website starts with (superusers).

The dashboard shows the conference record and its tracks, the website and its pages, the important
dates, the people (website organisers, programme chairs and editors, proceedings editors), the
programme, the proceedings (production, archive, DOIs) and recent activity. Its actions are for
superusers, each with a confirmation page:

| Action | What it does |
| --- | --- |
| Create the website | The home page at `/<year>/` with the standard pages below it, all as drafts, the conference days as the first important date, the group **IGLC nn organisers** and the collection **IGLC nn**. |
| Publish… | Publishes the pages ticked (their latest drafts); the home page comes with them. |
| Unpublish… | Takes the home page and all pages below it off the public site; the drafts stay. |
| Mark as current… | Served at the site's main address (only while published); unmarks the others. |
| Freeze… / Unfreeze… | After the conference: the organisers can no longer change anything. |
| Add an existing account / Invite someone new / Remove | The website organisers. An invitation makes an account (user name = e-mail address) and sends a link to choose a password; no password is sent or shown. |
| Start the programme… | The programme with its usual parts and a group of editors for each. |
| Show in / Hide from the archive… | The proceedings in the public archive (publishing through the production does this by itself). |
| Delete… | See below. |

**Deleting a conference** lists what goes with it (the website with its pages, the programme, an
empty production, the organisers group, an empty collection) and deletes it in one go, the website
through Wagtail so that the page tree stays consistent. It is refused while the conference has
papers or Crossref deposits (DOIs must keep working), a production with papers, or a published or
frozen website (unpublish or unfreeze it first).

## Setting up a conference's website (IGLC)

1. Conferences → All conferences → Add conference, with its number, city, country and dates, and the
   tracks. It stays out of the public archive until its proceedings are published.
2. On its dashboard: **Create the website**. The standard pages come from Conferences → Website
   standard pages; changes there apply to sites created afterwards. Delete the ones that are not
   needed (All pages → the page → Delete).

   From the command line instead: `python manage.py seed_conference_site 35 --current`.
   Creating the home page under Pages → IGLC conferences → Add child page also works, but does not
   add the conference days to the important dates.
3. People → **Invite someone new** for each organiser (or add an existing account). They log in at
   `/manage/`.
4. When the organisers and chairs are ready: **Publish…**, and **Mark as current…** when it should be
   the conference at the site's main address.

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

**Freeze…** the website on the dashboard: organisers can no longer change anything, and the site says that the
conference has taken place and links to its proceedings. The archive's conference page links to the
website ("Conference website") as long as it is published.

## The programme

Sessions, chairs, locations and papers are entered under Conferences → Programmes, by the
conference chairs and each part's editors (not the organisers, who keep the locations). The
programme page shows them with the "Programme" block. See docs/programme.md, which also has what
comes next: the registration backing of papers and program.iglc.net.
