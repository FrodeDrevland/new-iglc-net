# URL inventory

Every URL pattern the old iglc.net answers (ASP.NET MVC 5, 2014 to 2026), taken from its controllers and views, and how the new site handles it.
The old site matched URLs case-insensitively, and the default route `{controller}/{action}/{id}` also accepted `?id=`. The new site redirects both forms with a 301 (see `apps/archive/legacy.py`).

To inventory the actual URLs, including every paper and the URLs registered with Crossref, run the script on a machine that can reach iglc.net:

```
python tools/url_inventory.py crawl --out inventory/crawl.csv
python tools/url_inventory.py crossref --mailto <your email> --out inventory/crossref.csv
```

Then check the new site against both lists:

```
python tools/url_inventory.py check inventory/crawl.csv inventory/crossref.csv --base http://localhost:8000
```

## Proceedings archive (must keep working)

| Old URL | New URL | Status |
| --- | --- | --- |
| `/Papers`, `/Papers/Index` | `/papers` | Done |
| `/Papers/Conference/{id}` | `/papers/conference/{id}` | Done |
| `/Papers/Details/{id}` (Crossref resource URL) | `/papers/details/{id}` | Done |
| `/papers/details/{id}/pdf` (redirects to the PDF in blob storage) | same | Done |
| `/papers/details/{id}/presentation` | same | Done |
| `/Papers/PDF/{id}`, `/Papers/Presentation/{id}` | `/papers/details/{id}/pdf`, `.../presentation` | Done |
| `/Papers/Search` (GET form, POST `query`) | `/papers/search?q=` (POST still accepted) | Done |
| `/Papers/FindByConftoolId?year=&id=` | same, lower case | Done |
| `/Papers/ExportBibtex/{id}`, `/Papers/ExportRis/{id}` | same, lower case | Done |
| `/Papers/ExportConferenceBibtex/{id}`, `/Papers/ExportConferenceRis/{id}` | same, lower case | Done |
| `/Papers/ExportSearchBibtex?query=`, `/Papers/ExportSearchRis?query=` | same, lower case | Done |
| `/Papers/ExportCompleteBibtex`, `/Papers/ExportCompleteRis` | same, lower case | Done |
| Any of the above with `?id=` instead of `/{id}` | the `/{id}` form | Done |

The PDF links redirect to the full-text URL stored on each paper, which today points to Azure Blob Storage. Those blob URLs are also linked directly from other sites, so the storage account and container names should be kept, or redirected, when files move.

The old conference page also listed a ZIP of all papers (`papers-zipped` container) and full proceedings PDFs (`proceedings` container, files named `Proceedings-IGLC{number}*.pdf`). Not yet ported.

## Crossref findings (inventory/crossref.csv, September 2026)

1,340 DOIs are registered under 10.24928, all from 2017 (IGLC 25) to 2026 (IGLC 34). Papers from 1993 to 2016 have no DOIs.

| Points to | DOIs | New site |
| --- | --- | --- |
| `http://iglc.net/Papers/Details/{id}` (paper IDs 1367 to 2595) | 1,213 | Redirects to `/papers/details/{id}` |
| `http://iglc.net/Papers/Conference/{id}` (conference IDs 27 to 36, one per volume) | 10 | Redirects to `/papers/conference/{id}` |
| `http://itc.scix.net/cgi-bin/works/Show?_id=lc3-2017-...` (DOIs `10.24928/jc3-2017/...`, all 2017) | 117 | Not on iglc.net; unaffected by the switch |

- Every registered URL uses `http://iglc.net` with capitals. They all keep working through redirects, but should be updated to `https://www.iglc.net/papers/...` in a bulk Crossref update after the switch.
- The 117 `jc3-2017` DOIs depend on itc.scix.net staying online. If those papers are also in the IGLC archive, they could be pointed to iglc.net instead.
- No DOI is registered twice, and no two DOIs share a URL.

## Crawl findings (inventory/crawl.csv, September 2026)

10,581 URLs found. All 2,535 paper pages and all 31 published conference pages were reached, which matches the database.

- **PDFs and presentations:** 2,827 links redirect to `iglcstorage.blob.core.windows.net`. The new site redirects to the same stored URLs.
- **Files served from the site itself** (not blob storage), which need a new home and redirects from their old paths:
  - `/Content/Proceedings/`: 12 full proceedings PDFs (2015 to 2024)
  - `/Content/Documents/`: 3 standards PDFs and 4 IGLC33 author templates and forms
- **Errors on the live site today:** papers 55, 422 and 2226 return a server error (500). Paper 2226 has a registered DOI (10.24928/2024/0164), so that DOI currently leads to an error page.
- **Broken links on the live site:** relative `index.html` links (6 pages), `/Index/Papers` on the Proceedings page, `/ForAuthors/FormattingRequirements?view=...`, and a Cloudflare email-protection link. None need to be kept.

## Content pages (redirect to new Wagtail pages)

`python manage.py import_legacy_pages` creates these pages in Wagtail from the old views (converted by `tools/convert_legacy_pages.py` into `apps/pages/legacy_content/pages.json`). `/Links` is not a CMS page; it will be generated from the link database.

| Old URL | New URL |
| --- | --- |
| `/`, `/Home`, `/Home/Index` | `/` |
| `/Home/About` | `/about/` |
| `/Home/CharterAndOperatingProcedures` | `/charter-and-operating-procedures/` |
| `/Home/Standards` | `/standards/` |
| `/Home/Contact` | `/contact/` |
| `/Home/Copyright` | `/copyright/` |
| `/Home/Referencing`, `/Referencing`, `/ForAuthors/Referencing` | `/for-authors/referencing/` |
| `/ForAuthors`, `/ForAuthors/Index`, `/ForAuthors/ShowView` | `/for-authors/` |
| `/ForAuthors?view=X` (About, ContentRequirements, CopyrightPolicy, EthicsAndMalpracticeStatement, FormattingRequirements, Keywords, PaperStructure, PaperSubmissionAndReviewProcess, Publication, PublicationSchedule, Referencing, Templates) | `/for-authors/x-in-kebab-case/` |
| `/ForAuthors/Templates`, `/PaperStructure`, `/EthicsAndMalpracticeStatement` | `/for-authors/templates/` and so on |
| `/Home/ActiveConference`, `/Home/active-conference`, `/ActiveConference` | `/active-conference/` (later conference.iglc.net) |
| `/ActiveConference/CallForPapers`, `/FollowingConference` | `/active-conference/call-for-papers/`, `/active-conference/following-conference/` |
| `/ActiveConference/ConferenceWebsite` | `https://www.iglc-conference.com/` (the old page only forwarded there) |
| `/Links`, `/Home/important-links`, `/Community/Links` | `/links/` |
| `/Community/Coaching` | `/community/coaching/` |
| `/Community/MailingList` | `/community/mailing-list/` |
| `/Anniversary`, `/Anniversary/SvenBertelsen80` | `/anniversary/`, `/anniversary/sven-bertelsen-80/` |
| `/InMemoriam`, `/InMemoriam/SvenBertelsen` | `/in-memoriam/`, `/in-memoriam/sven-bertelsen/` |
| `/Proceedings` (full proceedings PDFs) | `/proceedings/` |
| `/Errors/Error404` | `/` |

## Replaced, not kept

| Old URL | New URL |
| --- | --- |
| `/Admin/...` (old admin area) | `/cms/` (Wagtail) |
| `/Account/...` (login, register, password) | `/cms/login/` |
| `/DataPunching/...`, `/Authors/...` (admin tools) | `/manage/` (Django admin) |
| `/Papers/Edit/{id}`, `/Papers/ResetFriendlyFileName/{id}` | `/manage/archive/paper/{id}/change/` (not redirected) |

## New site admin

- `/manage/`: Django admin for the archive (papers, authors, conferences, links).
- `/cms/`: Wagtail for content pages.
