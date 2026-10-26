# Condensed Matter Literature

Bilingual daily literature digest for an experimental quantum-materials researcher, including original theory and experiment. Published with GitHub Pages.

## Sources and scope

Discovery is restricted to Nature, Science, Nature Materials, Nature Communications, Nature Physics, PRX, Science Advances, PNAS, PRL, and arXiv. DOI-matched metadata services and matching preprints only recover missing abstracts for these journal articles.

- Soft matter is excluded by primary arXiv category and semantic screening.
- arXiv accepts only explicit **v1** entries from the current announcement's new/cross submissions. Replacements, unknown versions, stale announcements, and quantum gases are excluded.
- arXiv also requires substantive quantum-materials physics and a score of at least **70**: superconductivity, correlated electrons, quantum magnetism, topological electronic matter and related collective phenomena. Routine materials optimization and generic classical statistical mechanics do not qualify.
- Journals have no scientific title-keyword prefilter. Abstracts are recovered before AI judgment; unresolved records are deferred and retried.
- Experimental interest and scientific importance drive a joint editorial selection of **at most 30 articles**. Original theory remains eligible. Zero selections are allowed.

## Generate and re-screen

Requires Python 3.12 and OPENAI_API_KEY. The configured AI model remains gpt-6-luna.

Run `python update_daily.py` to harvest candidates and rebuild today's joint selection. Same-day candidates and valid assessments are reused, and newly discovered papers are included. Run `python update_daily.py --rescreen` to reassess every candidate. A rule-version change invalidates cached assessments.

Historical re-screening uses `python update_daily.py --date YYYY-MM-DD --rescreen` and requires a saved audit snapshot for that date. It never substitutes today's arXiv feed for a historical date.

The GitHub Actions workflow exposes date and rescreen inputs. A push to main regenerates today's issue, validates scope/version/size constraints, rebuilds bilingual reports and the website, and deploys Pages.

Each issue records its rules, thresholds, generation time, and intake dates. `audits/YYYY-MM-DD.json` preserves candidates, assessments, exclusions, pending abstracts, and source status. Source or AI assessment failure preserves the previously published issue.

## Checks and site

Run `python -m unittest -q test_relevance test_pipeline`.

The site is generated from `issues/*.json` and `site_template.html` with `python build.py`. Reports use `python make_reports.py` (WeasyPrint and Noto CJK fonts). GitHub Pages source: GitHub Actions.

