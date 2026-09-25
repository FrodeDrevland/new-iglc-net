# The conference programme

The plan for the programme of each IGLC conference: sessions, rooms, chairs and papers, and the
check that every presented paper is backed by a registration. This is phase 3, second step. Agreed
with the General Secretary, September 2026. Development steps 1 to 5 are built, except presenters from the
IGLC's own submission system, which waits for that system (2028).

Code: `apps/programme`. Back office: Manage → Conference programme (`/manage/programme/`).

## Using it

1. **Start the programme** (superusers): Manage → Conference programme → Start a programme, with
   the conference and its time zone (e.g. Europe/Berlin). This creates the four parts and the groups
   IGLC nn conference chairs, scientific chairs, industry day chairs, workshop day chairs and PhD
   summer school deans. The conference must have its dates in the archive.
2. **Add people to the groups** (Settings → Groups, or on the user). Membership gives access to the
   back office. The organisers' group of the conference website already exists.
3. **Parts and settings** (conference chairs): the status (hidden, provisional, final), the time
   zone, the first and last day (earlier for a PhD summer school before the conference), and the
   parts: rename, recolour, make public or not, add or delete. A new part gets its own group of
   editors when saved.
4. **Locations** (organisers and conference chairs), with map links and floor plans.
5. **Sessions** (each part's editors): time, location, kind, plenary, people, and the papers with
   their presenters; **Papers** adds several unplaced papers to a session at once. The overview
   lists the checks below.
6. **Registrations** (organisers, conference chairs, chief editors): upload the export of
   registrations (Excel or CSV) under Registrations, as often as there is a newer one, and tick the
   registration types that back papers (the technical/academic conference). New types start
   unticked and are flagged.
7. **Backing of the papers** (conference chairs and the chief editors of the proceedings; the
   organisers can look): set the deadline for authors and, if wanted, edit the email texts; then
   ask the authors, remind those who have not answered, and warn the papers without backing. The
   report shows every paper's backing, the authors' answer and where it is in the programme; a
   backer the matching misses can be chosen by hand; papers still without backing after the
   deadline are withdrawn from the same page (published papers cannot be withdrawn there).
   The authors answer on the main site, under /for-authors/confirm-presentation/ and their secret link.
8. **On the website**: a "Programme" block on a conference page shows the programme once it is not
   hidden (all public parts, or one part, e.g. for an industry day page). New conference sites get it
   on their programme page; on an existing site, add the block to the programme page. Each day is a
   grid of locations by time on large screens and a list on phones and in print. Below the
   programme page there are pages for each day (/2027/programme/day/2027-07-20/), session, location
   (with its map link and floor plan) and public part. A part that is not public has a private link
   (/2027/programme/private/...), shown on the programme's overview in the back office to its editors
   and the conference chairs; its pages are not indexed by search engines.


## What the programme holds

- **Programme**: one per conference (the archive's conference record), with its time zone (for
  calendar files), its status (hidden, provisional or final) and when it last changed.
- **Parts**: academic conference, industry day, workshop day and PhD summer school (a conference
  may have fewer, or others). A part has a name, a colour, a short description, a **public** flag
  and its own group of editors. A part that is not public is shown only through a private link;
  the PhD summer school starts as not public.
- **Locations**: rooms at the venue and places elsewhere (the conference dinner). Name, building or
  floor, capacity, a **map link** (Mazemap, Google Maps or the venue's own), an optional floor plan,
  an address for places off the venue, and an accessibility note.
- **Sessions**: part, day, start and end, location, code (for example 3B), title, kind (paper
  session, poster session, keynote, panel, workshop, industry session, break, meal, social event,
  Annual Business Meeting, other), optional track and notes, and a **plenary** flag.
- **Session people**: name and affiliation with a role (chair, co-chair, facilitator, moderator,
  panellist, speaker), optionally linked to the person's author page.
- **Session items**, in order: an accepted paper with its presenter and its form of presentation
  (**talk** or **poster**), or a free item (title and speaker). Talks may have minutes; posters may
  have a board number.
- Keynote sessions link to the speakers on the keynotes page, so name, photo and talk are entered once.

Rules the back office enforces or warns about:

- Every session has a location, except breaks (optional). A plenary session must have one.
- Warning when anything in the same part runs in parallel with a plenary session.
- Two sessions in one location at the same time.
- A chair or presenter in two sessions at the same time. Chairing a session and presenting in the
  same session is allowed (a note suggests a co-chair for that slot).
- A paper not yet placed, or placed twice; a withdrawn paper still in a session.
- More talks than a session has time for; sessions outside the conference days.

Posters are a form of presentation, not a separate kind of contribution: every poster is backed by
a paper, and the rules for backing, presenters and confirmation are the same as for talks.

## Who edits what

The programme is not edited by the organiser group (which runs the website pages). Each conference
gets these groups when its programme is set up; the IGLC adds people to them. One person may be in
several.

| Group | May edit |
|---|---|
| IGLC nn conference chairs | every part, and the locations |
| IGLC nn organisers | the locations (as well as the website pages) |
| IGLC nn scientific chairs | the academic conference: paper and poster sessions, session chairs, presenters, breaks and meals |
| IGLC nn industry day chairs | the industry day |
| IGLC nn workshop day chairs | the workshop day |
| IGLC nn PhD summer school deans | the PhD summer school |

Everyone who edits a part chooses locations from the list. Nobody sees or edits another
conference's programme. When the conference website is frozen, the programme is frozen too.

## The papers

Session items point to the paper in the proceedings production (the Submission), not to a copy.
Before publication the title, track and authors come from ConfTool's export; once the paper is
published, the same item links to its page, DOI and PDF, with nothing retyped. The paper's page
says in which session it was presented. The order of the proceedings stays by track and does not
follow the programme.

Session planning is done here, not in ConfTool.

## Registration backing and confirmation

The IGLC rule: every paper must be backed by a registered author, and one registration backs at
most two papers. A backed paper is published in the proceedings even if it is not presented.

1. **Registrations.** Registration and payment stay outside the platform. The organisers upload an
   export of registrations (CSV or Excel, columns found by their headings, as for ConfTool):
   name, email, registration type, paid. Uploads may be repeated. Only registrations for the
   technical/academic conference count; the organisers mark which registration types those are.
   The registration system for IGLC 35 is not chosen yet (possibly ConfTool).
2. **The check.** Authors are matched to registrations by email, then by name; editors can link
   them by hand. The system looks for an assignment in which every paper has a backer and no
   registration backs more than two papers, and lists the papers that cannot be backed.
3. **Confirmation.** Every author of every paper gets a private link (the same kind as for the
   metadata check) to say whether the paper will be presented, by whom (a registered author) and
   which registered author backs it. Any author may answer; the co-authors are told, and every
   answer is kept.
4. **Warnings.** The chief editors send the authors of papers without backing a warning, from an
   editable text with the deadline filled in, and reminders. Every email sent is recorded.
5. **Withdrawal.** After the deadline the chief editors withdraw the papers still without backing,
   by hand, from a list.

| The paper is | Then |
|---|---|
| backed and presented | placed in the programme with its presenter |
| backed, not presented | published in the proceedings, not placed |
| not backed at the deadline | warned, then withdrawn |

This must be finished before the papers are published (page numbers follow from what remains), and
it needs outgoing email from iglc.net.

## Where it is shown

- **conference.iglc.net/2027/programme/** (one per year), the canonical address: the "programme" standard
  page becomes a programme page drawn from the data, with views by day, session, location and part,
  a grid of locations by time on large screens and cards on phones, a print version and calendar
  files. Each part can also have its own page (industry day, workshop day, PhD summer school).
- **program.iglc.net**: the current conference at the venue: now and next, today, my programme.
  Short enough to print on badges and room signs. On the preview: program.iglc.drevland.net,
  password-protected and noindex like the rest.

After the conference the frozen programme stays as the record of what was presented.

## At the venue

- **program.iglc.net** (program.iglc.drevland.net on the preview; its host name follows `SITE_URL`,
  or the setting `PROGRAMME_HOST`) shows the current conference's programme for phones: **Now**
  (what is on and what comes next, and the latest changes), **Day**, **Mine** and **All** (the
  conference site's programme page). The same pages are on the conference site under
  /2027/programme/now/, /today/ and /my/, for any year. Adding `?at=2027-07-20T10:45` to the
  address shows the Now page at another moment, for trying it out.
- **My programme**: a star on every session. The choice is kept in the visitor's browser only (no
  login, nothing sent to the site), and can be added to a calendar.
- **Calendar files**: the whole programme (/2027/programme/calendar.ics), a part (?part=), a private
  part (?k= its private link), a visitor's own sessions, and one session (on its page). Calendar apps
  that subscribe fetch them again, so changes and cancellations reach them. Breaks are left out.
- **Late changes**: a session can be marked cancelled (struck through, and cancelled in calendars)
  or given a change note, e.g. "Moved to Room 103"; both are dated and listed under Now. A notice
  (Parts and settings) is shown at the top of every programme page.
- **Room signs**: Locations → Room signs (PDF), one A4 page per location with a QR code for its page
  on the conference site (what is on there, and its map).

## Extras

- **Plan by dragging** (programme overview): one day at a time, drag papers from the list of papers
  not placed into paper and poster sessions, between sessions, back to the list, and into order;
  then save. A paper dragged into a poster session becomes a poster. Keyboard users use Papers and
  the session pages instead.
- **Booklet**: the programme as an A5 PDF (title page, parts, every day's sessions with chairs,
  papers and presenters, late changes, locations, and an index of people with their sessions), at
  /2027/programme/programme.pdf and on program.iglc.net, and in the back office (Booklet (PDF)) also
  while the programme is hidden. It uses the proceedings' Times New Roman where the site has it,
  else Helvetica.
- **Offline**: once a visitor has opened the programme (on program.iglc.net, or the programme page on
  the conference site), their browser keeps its pages, so they open without a network; the pages
  are fetched again when the programme changes. The venue pages say when they are shown offline.
- **Slides**: authors upload their slides (PDF or PowerPoint, up to 50 MB) on the same secret-link
  page as their answer. They are shown with the paper in the programme and put on the published
  paper's page (its Presentation button); for papers published later, Backing of the papers → "Put
  them on the published papers' pages".

## Development steps

1. **Back office** (built): the models, locations, parts with their editor groups and public flag,
   sessions (plenary and poster sessions included), papers placed as talks or posters, the checks
   above, and a programme block for the conference pages.
2. **Registration backing** (built): registration import, the backing check, the authors'
   confirmation links, warnings and withdrawal. Sending needs email on iglc.net.
3. **Public programme** (built): the pages on the conference site, with a "provisional" banner
   until the programme is final.
4. **At the venue** (built): program.iglc.net, now and next, my programme (kept in the visitor's
   browser, no login), calendar files and subscribable feeds, QR codes for room signs, marks for
   changed and cancelled sessions, and a notice banner.
5. **Extras** (built, see above): the PDF booklet, working offline at the venue, drag-and-drop
   planning and presenters' slide uploads. Presenters from the IGLC's own submission system follow
   with that system (2028).

The IGLC 35 programme is to be public in June 2027.

## Tests

- Validation: clashes of locations, chairs and presenters; plenary without location; a paper placed
  twice; sessions outside the conference days.
- Permissions: each group edits only its parts, organisers only locations, nothing of another
  conference; frozen means no edits.
- A paper's item links to the published paper after publication; withdrawn papers are flagged.
- Backing: the two-paper limit, papers that can be backed only through a co-author, registration
  types that do not count, unpaid registrations.
- Calendar files: times in the conference's time zone.
- The pages on the conference host and on program.iglc.net, with no main-site URL names reversed;
  parts that are not public and hidden programmes are not shown; the preview stays noindex.
