# Condensed Matter Literature

Bilingual daily literature digest for an experimental quantum-materials researcher, including original theory and experiment. Published with GitHub Pages.

## Sources and scope

Discovery is restricted to Nature, Science, Nature Materials, Nature Communications, Nature Physics, PRX, Science Advances, PNAS, PRL, and arXiv. DOI-matched metadata services and matching preprints only recover missing abstracts for these journal articles.

- Soft matter is excluded by primary arXiv category and semantic screening.
- arXiv accepts only explicit **v1** entries from the current announcement's new/cross submissions. Replacements, unknown versions, stale announcements, and quantum gases are excluded.
- arXiv also requires substantive quantum-materials physics and a score of at least **70**: superconductivity, correlated electrons, quantum magnetism, topological electronic matter and related collective phenomena. Routine materials optimization and generic classical statistical mechanics do not qualify.
- Journals accept only publisher-verified research articles/letters formally published online on the issue date. Acceptance dates and Crossref online dates alone are insufficient. APS publication is verified from its official final-citation feed; formally published APS entries are discovered there even when their Crossref acceptance date was earlier.
- Essay, Reply, Comment, reviews, news and corrections are excluded before abstract recovery. Unknown article types or unverified publication states never enter the recommendation list.
- Journals have no scientific title-keyword prefilter. Reliable abstracts are recovered after document/publication verification. Missing abstracts may be retried on the same publication day; older publications are not backfilled into a new day's issue.
- DOI, arXiv identity and normalized-title aliases deduplicate the same work across sources and previously published issues.
- Experimental interest and scientific importance drive a joint editorial selection of **at most 30 articles**. Original theory remains eligible. Zero selections are allowed.

## Generate and re-screen

Requires Python 3.12 and OPENAI_API_KEY. The configured AI model remains gpt-6-luna.

Run `python update_daily.py` to harvest candidates and rebuild today's joint selection. Publication eligibility is verified on every run. Same-day candidates and valid assessments are reused, and newly discovered papers are included. Run `python update_daily.py --rescreen` to reassess every candidate. Scientific assessments have a separate rubric version: publication-gate changes revalidate eligibility without needlessly repeating unchanged scientific assessments; rubric changes invalidate them.

Historical re-screening uses `python update_daily.py --date YYYY-MM-DD --rescreen` and requires a saved audit snapshot for that date. It never substitutes today's arXiv feed for a historical date.

The GitHub Actions workflow exposes date and rescreen inputs. A push to main regenerates today's issue, validates scope/version/size constraints, rebuilds bilingual reports and the website, and deploys Pages.

Each issue records its rules, thresholds, generation time, and intake dates. `audits/YYYY-MM-DD.json` preserves candidates, assessments, exclusions, pending abstracts, and source status. Source or AI assessment failure preserves the previously published issue.

## Checks and site

Run `python -m unittest -q test_relevance test_pipeline`.

The site is generated from `issues/*.json` and `site_template.html` with `python build.py`. Reports use `python make_reports.py` (WeasyPrint and Noto CJK fonts). GitHub Pages source: GitHub Actions.



## Scheduled publication and recovery

The primary schedule is 06:00 America/Los_Angeles, leaving three hours before the desired 09:00 publication deadline. Additional scheduled attempts run at minutes 17 and 47 from 06:00 through 12:00. The schedule follows Los Angeles daylight saving time. GitHub can delay or omit scheduled triggers; starting earlier provides extra time but does not guarantee publication before 09:00.

Scheduled runs first inspect the saved source audit. If arXiv previously returned an older announcement, a lightweight listing-date check runs before the issue can be treated as final. A newly available announcement for the issue date resumes harvesting and editorial selection while reusing valid AI assessments. An unchanged listing skips paid screening but records the pending source; a failed source-date check fails the run and preserves the live issue for retry.

Scheduled runs compare the saved daily issue with the live website. If both match, all generation/deployment work is skipped. If today's validated JSON exists but is not yet live, the run resumes publication without repeating paid scientific screening. A missing/invalid issue is generated normally. Overlapping scheduled retries wait rather than cancelling an active release.

Every actual deployment checks the live website against the saved issue content. A failed verification fails the workflow rather than reporting publication as complete. Pushes and explicit manual runs continue to support deliberate regeneration.

## Independent cloud trigger

A cloud scheduler can call the existing workflow-dispatch endpoint with:

```json
{"ref":"main","inputs":{"reuse_valid_issue":true}}
```

Use America/Los_Angeles time, with 06:00 as the first attempt and 08:00 as the recovery attempt. The trigger credential needs only Actions read/write on this repository. Keep it in the scheduler's Authorization header, never in this repository, a URL, or a chat message.

Cloud recovery checks today's validated issue and live page. It generates a missing issue, resumes an unfinished deployment, or skips work that is already published. Pending arXiv announcements are still rechecked. Explicit rescreen overrides reuse. Recovery triggers wait for an active run rather than cancelling it, and scheduled/recovery runs check out the current branch head so queued attempts see the preceding run's saved issue.

An HTTP success from the dispatch endpoint confirms acceptance of the trigger. Actual publication is separately verified by the workflow's final live-site check. This independent trigger bypasses GitHub cron delivery; it does not establish a fix to GitHub's scheduler or provide an uptime guarantee.
