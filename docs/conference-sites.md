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
  conference opens its workspace.
- **Programmes** and **Proceedings production**: the programme and the proceedings of each conference
  (docs/programme.md, docs/production-process.md).
- **Website standard pages**: the pages every new conference website starts with (superusers).

The Overview shows the conference record and its tracks, the website and its pages, the important
dates, the people (website organisers, programme chairs and editors, proceedings editors), the
programme, the proceedings (production, archive, DOIs) and recent activity. Its actions are, unless said otherwise, for
superusers, each with a confirmation page:

| Action | What it does |
| --- | --- |
| Create the website | The home page at `/<year>/` with the standard pages below it, all as drafts, the conference days as the first important date, the group **IGLC nn organisers** and the collection **IGLC nn**. |
| Publish… | Publishes the pages ticked (their latest drafts); the home page comes with them. |
| Unpublish… | Takes the home page and all pages below it off the public site; the drafts stay. |
| Mark as current… | Served at the site's main address (only while published); unmarks the others. |
| Freeze… / Unfreeze… | After the conference: the organisers can no longer change anything. |
| Add someone / remove | People in each role (see Roles). A new person gets an account (user name = e-mail address) and a link to choose a password; no password is sent or shown. Conference chairs may do this too, except for the chairs themselves. |
| Start the programme… | The programme with its usual parts and a group of editors for each. |
| Show in / Hide from the archive… | The proceedings in the public archive (publishing through the production does this by itself). |
| Delete… | See below. |

**Deleting a conference** lists what goes with it (the website with its pages, the programme, an
empty production, the organisers group, an empty collection) and deletes it in one go, the website
through Wagtail so that the page tree stays consistent. It is refused while the conference has
papers or Crossref deposits (DOIs must keep working), a production with papers, or a published or
frozen website (unpublish or unfreeze it first).

## The conference workspace

Each conference has its own part of the back office at `/manage/<number>/` (code:
`apps/conferences/workspace.py` and `workspace_views.py`). Inside it the sidebar shows only that
conference: **Overview**, **Website** (its pages with Edit buttons, publishing), **Dates and links** (the
important dates, the registration link and the contact e-mail, saved as a draft of the home page or
published), **Committees** (the members of the committees page, with portraits, one table per committee;
add one or paste many; saved as drafts of that page), **Branding** (the
home page's logo, photograph, colours and font, saved as a draft or published), **People**,
**Programme**, **Proceedings**, Images, Documents and Help (Submission and review joins them in
phase 5). The first item switches to another conference or, for the IGLC's own people, back to
**IGLC admin** (the full menu, with the same switcher on top). The conference's programme
and production pages, and the page editor of one of its pages, count as inside it; Images,
Documents and Help belong to the conference last visited.

People whose only roles are in conferences never see the IGLC administration: `/manage/` takes
them to their conference. For everyone but superusers, Wagtail's page tree of a conference page
leads to its Website page, and publishing, unpublishing or deleting a page in the editor comes back
to it.

## Roles

Each conference has its people, managed under People in its workspace (code: `apps/conferences/roles.py`):

| Role | Group | May |
| --- | --- | --- |
| Conference chairs | IGLC nn conference chairs | Edit and publish the website, the whole programme, add and remove organisers and part chairs |
| Scientific chairs | IGLC nn scientific chairs | The proceedings as chief editors (apps/production/access.py), and the academic conference's sessions |
| Website organisers | IGLC nn organisers | Edit and publish the website, upload pictures and documents, the programme's locations |
| Other part chairs | IGLC nn industry day chairs, workshop day chairs, PhD summer school deans | Their part of the programme (made when the programme is started) |
| Proceedings editors | the production's editor list | The proceedings |

Everyone with a role sees the conference's Overview and People. Only the IGLC appoints conference
chairs and scientific chairs. Adding someone is by e-mail address: an existing account gets the role,
someone new gets an account and a link to choose a password. Superusers can do everything; only they
create and delete the website, mark it as current, freeze it, or change the archive. The guide for
the people themselves is docs/conference-organisers.md (Help → Site documentation).

## Setting up a conference's website (IGLC)

1. Conferences → All conferences → Add conference, with its number, city, country and dates, and the
   tracks. It stays out of the public archive until its proceedings are published.
2. In its workspace (All conferences → the conference): Website → **Create the website**. The standard pages come from Conferences → Website
   standard pages; changes there apply to sites created afterwards. Delete the ones that are not
   needed (All pages → the page → Delete).

   From the command line instead: `python manage.py seed_conference_site 35 --current`.
   Creating the home page under Pages → IGLC conferences → Add child page also works, but does not
   add the conference days to the important dates.
3. People → **Add someone** under Conference chairs and Website organisers. They log in at `/manage/`;
   point them to the guide for conference organisers.
4. When the organisers and chairs are ready: **Publish…**, and **Mark as current…** when it should be
   the conference at the site's main address.

## What the organisers do

- Edit and **publish** the pages themselves (Publish in the menu under Save draft), no IGLC approval
  needed; they can also unpublish. They cannot change the current/frozen settings,
  delete the site, or touch other conferences' pages.
- Branding (in the conference's menu, `/manage/<number>/branding/`, with a preview of the home page): the photograph (and whether to darken it), a logo on the photograph (instead of the title), a logo in the header (without one: the IGLC symbol, white or black to suit the main colour, and the name), two colours, the heading font, a logo on light backgrounds (the archive's conference page, link previews) and a square icon (browser tab, home screen). The platform says where each logo is shown; the organisers choose a version that reads well there. The layout
  stays the IGLC's (responsive and accessible); the text on the main colour is white or black, whichever reads better, and links and headings use a darker shade of a light main colour.
  Fonts are served by the site itself, not by a font service.
- Preview: the eye icon in the page editor, or Preview next to a page under Website (the latest draft; in a preview the website's menu has the draft pages too, linking to their drafts).
- Important dates are entered once, under Dates and links (kept in date order), and shown wherever a page has an
  "important dates" block. An extended deadline keeps the old date, struck through.

## From the platform

- Conference number, city and dates, and the tracks: the conference record in the archive.
- Accepted papers: the papers the IGLC has from ConfTool for the proceedings (withdrawn papers left
  out, no e-mail addresses); after publication, the published papers with links.
- The proceedings editors, on the committees page (can be switched off).

## After the conference

**Freeze…** the website (Website in its workspace): organisers can no longer change anything, and the site says that the
conference has taken place and links to its proceedings. The archive's conference page links to the
website ("Conference website") as long as it is published.

## The programme

Sessions, chairs, locations and papers are entered under Conferences → Programmes, by the
conference chairs and each part's editors (not the organisers, who keep the locations). The
programme page shows them with the "Programme" block. See docs/programme.md, which also has what
comes next: the registration backing of papers and program.iglc.net.
