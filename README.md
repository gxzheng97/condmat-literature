# Condensed Matter Literature

Bilingual daily literature digest for an experimental quantum-materials researcher, including original theory and experiment. Published with GitHub Pages.

## Sources and scope

Discovery is restricted to Nature, Science, Nature Materials, Nature Communications, Nature Physics, PRX, Science Advances, PNAS, PRL, and arXiv. DOI-matched metadata services and matching preprints only recover missing abstracts for these journal articles.

- Soft matter is excluded by primary arXiv category and semantic screening.
- arXiv accepts only explicit **v1** entries first announced inside the fixed 24-hour window ending at **06:00 America/Los_Angeles on the issue date**. Dated official catchup pages provide the announcement batch; author submission timestamps do not define the window. Cross-lists require a matching new-submission entry in the original category on that batch date, so an old v1 cannot re-enter as a fresh announcement. Replacements, unknown versions, announcements outside the window, and quantum gases are excluded.
- arXiv also requires substantive quantum-materials physics and a score of at least **70**: superconductivity, correlated electrons, quantum magnetism, topological electronic matter and related collective phenomena. Routine materials optimization and generic classical statistical mechanics do not qualify.
- Journals accept only publisher-verified research articles/letters formally published online on the **previous Los Angeles calendar day**. For example, the October 30 morning issue uses October 29 journal publication dates. Acceptance dates and Crossref online dates alone are insufficient. APS publication is verified from its official final-citation feed; formally published APS entries are discovered there even when their Crossref acceptance date was earlier. If the PRL recent feed is behind the target date, its official condensed-matter and Editors' Suggestions feeds provide additional final-citation evidence; audit source records preserve which feeds were used and the latest verified publication date.
- Essay, Reply, Comment, reviews, news and corrections are excluded before abstract recovery. Unknown article types or unverified publication states never enter the recommendation list.
- Journals have no scientific title-keyword prefilter. Reliable abstracts are recovered after document/publication verification. Missing abstracts may be retried within the same morning issue; the publication date must still match that issue's previous-day target.
- DOI, arXiv identity and normalized-title aliases deduplicate the same work across sources and previously published issues.
- Experimental interest and scientific importance drive a joint editorial selection of **at most 30 articles**. Original theory remains eligible. Zero selections are allowed.

## Generate and re-screen

Requires Python 3.12 and OPENAI_API_KEY. The configured AI model remains gpt-6-luna.

Run `python update_daily.py` to harvest candidates and rebuild today's joint selection. Publication eligibility is verified on every run. Candidates in the same intake window and valid assessments are reused, and newly discovered papers are included. Run `python update_daily.py --rescreen` to reassess every candidate. Scientific assessments have a separate rubric version: publication-gate changes revalidate eligibility without needlessly repeating unchanged scientific assessments; rubric changes invalidate them.

Historical re-screening uses `python update_daily.py --date YYYY-MM-DD --rescreen` and requires a saved audit snapshot with the matching intake window for that date. Snapshots from a different date policy are rejected so old archives are not silently relabelled. It never substitutes today's arXiv feed for a historical date.

The GitHub Actions workflow exposes date and rescreen inputs. A push to main regenerates today's issue, validates scope/version/size constraints, rebuilds bilingual reports and the website, and deploys Pages.

Each issue records its rules, thresholds, generation time, and `intake_window` (UTC start/end, Los Angeles timezone, and target journal publication date). The window always ends at local 06:00 and spans exactly 24 elapsed hours, including daylight-saving transitions. The 08:00 recovery uses the same window. The new policy starts with the October 30, 2026 morning issue. Existing v4 issues through October 29 remain valid under their original policy; recovery does not regenerate or relabel them. `audits/YYYY-MM-DD.json` preserves candidates, assessments, exclusions, pending abstracts, and source status. Source or AI assessment failure preserves the previously published issue.

## Checks and site

Run `python -m unittest -q test_relevance test_pipeline test_daily_release test_intake_window`.

The site is generated from `issues/*.json` and `site_template.html` with `python build.py`. Reports use `python make_reports.py` (WeasyPrint and Noto CJK fonts). GitHub Pages source: GitHub Actions.



## Scheduled publication and recovery

The primary schedule is 06:00 America/Los_Angeles, leaving three hours before the desired 09:00 publication deadline. Additional scheduled attempts run at minutes 17 and 47 from 06:00 through 12:00. The schedule follows Los Angeles daylight saving time. GitHub can delay or omit scheduled triggers; starting earlier provides extra time but does not guarantee publication before 09:00.

The arXiv harvest requests the issue date's official catchup page instead of relying on the mutable live `new` listing. An explicitly dated, empty page (maintenance, holiday or no announcement) is a valid zero; an unavailable, malformed or wrong-date response fails harvesting and preserves the previous issue. Later runs cannot absorb the following day's batch into this morning's window.

Scheduled runs compare the saved daily issue with the live website. If both match, all generation/deployment work is skipped. If today's validated JSON exists but is not yet live, the run resumes publication without repeating paid scientific screening. A missing/invalid issue is generated normally. Overlapping scheduled retries wait rather than cancelling an active release.

Every actual deployment checks the live website against the saved issue content. A failed verification fails the workflow rather than reporting publication as complete. Pushes and explicit manual runs continue to support deliberate regeneration.

## Independent cloud trigger

A cloud scheduler can call the existing workflow-dispatch endpoint with:

```json
{"ref":"main","inputs":{"reuse_valid_issue":true}}
```

Use America/Los_Angeles time, with 06:00 as the first attempt and 08:00 as the recovery attempt. The trigger credential needs only Actions read/write on this repository. Keep it in the scheduler's Authorization header, never in this repository, a URL, or a chat message.

Cloud recovery checks today's validated issue and live page. It generates a missing issue, resumes an unfinished deployment, or skips work that is already published. arXiv intake remains tied to the fixed dated batch. Explicit rescreen overrides reuse. Recovery triggers wait for an active run rather than cancelling it, and scheduled/recovery runs check out the current branch head so queued attempts see the preceding run's saved issue.

An HTTP success from the dispatch endpoint confirms acceptance of the trigger. Actual publication is separately verified by the workflow's final live-site check. This independent trigger bypasses GitHub cron delivery; it does not establish a fix to GitHub's scheduler or provide an uptime guarantee.
