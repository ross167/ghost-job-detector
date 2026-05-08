# Ghost Job Detector

**Assess whether a LinkedIn job listing is a ghost job before you apply.**

Up to 34% of advertised roles may be ghost jobs — vacancies posted with no genuine intention to hire. This tool analyses the text of any LinkedIn job listing and returns a ghost likelihood score, a full factor breakdown, and recommended actions.

Free. No API keys. No accounts. Nothing stored.

---

## Web tool

The easiest way to use this is the free web tool at **[ghostjobdetector.com](https://ghostjobdetector.com)**. Paste a listing, get a verdict in seconds.

---

## Python tool

The Python version is for developers, researchers, and anyone who wants to extend or integrate the scoring logic.

### Requirements

- Python 3.8+
- No mandatory dependencies

**Optional — enables company news search:**
```
pip install feedparser
```

### Installation

```bash
git clone https://github.com/yourusername/ghost-job-detector.git
cd ghost-job-detector
```

### Usage

**Interactive mode** — paste a listing directly into the terminal:
```bash
python ghost_job_detector_v2.py
```

**From a file** — pass a saved listing as a text file:
```bash
python ghost_job_detector_v2.py --file listing.txt
```

**JSON output** — machine-readable output for integration:
```bash
python ghost_job_detector_v2.py --file listing.txt --json
```

**With company news search** — pass the company name to enable Google News lookup:
```bash
python ghost_job_detector_v2.py --file listing.txt --company "Acme Corp"
```

### How to get the listing text

1. Open the job on LinkedIn as a full page, not a side panel
2. Click "Show more" to expand the full description if visible
3. Press Ctrl+A (Windows) or Cmd+A (Mac) to select all text
4. Copy and paste into the terminal or save to a text file

---

## What it analyses

| Factor | What it measures | Weight |
|---|---|---|
| **Posting age and history** | How long the role has been listed; whether LinkedIn marks it as reposted | 30% |
| **Description quality** | Word count; presence of generic template phrases; specificity of detail | 25% |
| **Salary and location transparency** | Whether a salary and work arrangement are disclosed | 20% |
| **Posting specificity and intent** | Whether the level of detail suggests a live brief or speculative outreach | 15% |
| **LinkedIn engagement signals** | Applicant count relative to posting age; company size signals | 10% |

---

## Traffic light verdicts

| Score | Verdict |
|---|---|
| 0-25% | Looks genuine |
| 26-60% | Worth a closer look |
| 61-100% | Likely a ghost job |

---

## JSON output schema

```json
{
  "ghost_likelihood_pct": 42,
  "verdict": "Worth a closer look",
  "summary": "Some concerns detected...",
  "detected": {
    "is_reposted": false,
    "days_posted": 18,
    "applicant_count": 34,
    "company_size_label": "51-200 employees",
    "work_type": "Hybrid",
    "has_salary": false,
    "is_easy_apply": true,
    "is_agency": false,
    "description_words": 312,
    "generic_phrase_count": 3,
    "specificity_signals": 2
  },
  "factors": [],
  "red_flags": [],
  "green_signals": [],
  "generic_phrases": [],
  "actions": []
}
```

---

## Extending the tool

The codebase is structured as four independent layers:

- **`parse_listing(text)`** extracts structured signals from raw LinkedIn text
- **`score_listing(parsed)`** applies weighted scoring and returns the full result dict
- **`search_company_news(company_name)`** optional Google News RSS lookup via feedparser
- **`print_report(result, articles, verdict)`** terminal report renderer

You can import and use any of these independently:

```python
from ghost_job_detector_v2 import parse_listing, score_listing

text   = open("listing.txt").read()
parsed = parse_listing(text)
result = score_listing(parsed)

print(f"Ghost likelihood: {result['pct']}%")
print(f"Verdict: {result['verdict']}")
```

---

## What this tool cannot assess

Some ghost job signals require external data not available from the listing text alone:

- How many times the role has been posted previously
- Whether the company has recently secured funding or announced expansion
- How many other roles the company currently has open relative to its headcount

These are flagged in the "Requires additional research" section of the report with guidance on where to check.

---

## Background

Ghost jobs are vacancies posted with no genuine intention of filling them. Companies list roles to build talent pipelines, signal growth to investors, or keep their profile active on job boards. Research cited by the BBC (2025) suggests up to 34% of advertised roles may fall into this category.

This tool was built by [Ross Wilson](https://rosswilson.consulting) to accompany a LinkedIn article on ghost jobs. The analysis was inspired by [David Mackenzie of Mackenzie Jones Group](https://www.linkedin.com/in/davidjmackenzie/).

---

## Disclaimer

Results are heuristic guides based on text signals, not definitive verdicts. A low score does not guarantee a role is genuine. A high score does not confirm it is fake. Always verify directly with someone at the company before concluding a role does not exist.

---

## Licence

MIT. Free to use, modify, and distribute with attribution.
