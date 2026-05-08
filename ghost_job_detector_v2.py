#!/usr/bin/env python3
"""
Ghost Job Detector v2.0 — LinkedIn Edition
===========================================
Paste the full text of a LinkedIn job listing and receive an assessment
of how likely it is to be a ghost job: a vacancy posted with no genuine
intention to hire.

Research suggests up to 34% of advertised roles may fall into this category.

Usage:
    python ghost_job_detector.py

Optional dependencies (enable company news search):
    pip install feedparser

Based on the web tool at https://ghostjobdetector.com
Built by Ross Wilson — https://rosswilson.consulting
"""

import re
import sys
import math
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Terminal colour helpers
# ---------------------------------------------------------------------------

RED    = "\033[91m"
ORANGE = "\033[38;5;208m"
GREEN  = "\033[92m"
AMBER  = "\033[93m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False


# ---------------------------------------------------------------------------
# Parser: extract structured signals from raw LinkedIn text
# ---------------------------------------------------------------------------

def parse_listing(text: str) -> dict:
    """Parse raw pasted LinkedIn listing text into structured signals."""
    p = {"raw": text}
    unit_days = {"hour": 1/24, "day": 1, "week": 7, "month": 30}

    # Posting age and repost status
    repost_m = re.search(
        r"\bReposted\s+(\d+)\s+(hour|day|week|month)s?\s+ago\b", text, re.IGNORECASE
    )
    posted_m = re.search(
        r"\bPosted\s+(\d+)\s+(hour|day|week|month)s?\s+ago\b", text, re.IGNORECASE
    )

    if repost_m:
        p["is_reposted"] = True
        p["days_posted"] = math.ceil(
            int(repost_m.group(1)) * unit_days.get(repost_m.group(2).lower(), 1)
        )
        p["post_label"] = (
            f"Reposted {repost_m.group(1)} {repost_m.group(2)}"
            f"{'s' if int(repost_m.group(1)) > 1 else ''} ago"
        )
    elif posted_m:
        p["is_reposted"] = False
        p["days_posted"] = math.ceil(
            int(posted_m.group(1)) * unit_days.get(posted_m.group(2).lower(), 1)
        )
        p["post_label"] = (
            f"Posted {posted_m.group(1)} {posted_m.group(2)}"
            f"{'s' if int(posted_m.group(1)) > 1 else ''} ago"
        )

    # Applicants
    if re.search(r"Be an early applicant", text, re.IGNORECASE):
        p["applicant_count"] = 0
        p["is_early_applicant"] = True
        p["applicant_label"] = "Be an early applicant"
    else:
        over_m  = re.search(r"Over\s+([\d,]+)\s+applicants?", text, re.IGNORECASE)
        count_m = re.search(r"([\d,]+)\+?\s+applicants?", text, re.IGNORECASE)
        if over_m:
            p["applicant_count"] = int(over_m.group(1).replace(",", ""))
            p["applicant_label"] = f"Over {p['applicant_count']:,} applicants"
            p["applicants_over"] = True
        elif count_m:
            p["applicant_count"] = int(count_m.group(1).replace(",", ""))
            p["applicant_label"] = f"{p['applicant_count']:,} applicants"

    # Company size
    size_range = re.search(r"([\d,]+)[–\-]([\d,]+)\s+employees", text, re.IGNORECASE)
    size_plus  = re.search(r"([\d,]+)\+\s+employees", text, re.IGNORECASE)
    if size_range:
        p["company_size_min"] = int(size_range.group(1).replace(",", ""))
        p["company_size_max"] = int(size_range.group(2).replace(",", ""))
        p["company_size_mid"] = (p["company_size_min"] + p["company_size_max"]) / 2
        p["company_size_label"] = f"{size_range.group(1)}–{size_range.group(2)} employees"
    elif size_plus:
        p["company_size_min"] = int(size_plus.group(1).replace(",", ""))
        p["company_size_mid"] = p["company_size_min"] * 1.5
        p["company_size_label"] = f"{size_plus.group(1)}+ employees"

    # Work type
    if re.search(r"\bRemote\b", text):
        p["work_type"] = "Remote"
    elif re.search(r"\bHybrid\b", text, re.IGNORECASE):
        p["work_type"] = "Hybrid"
    elif re.search(r"\bOn-?site\b", text, re.IGNORECASE):
        p["work_type"] = "On-site"

    # Easy Apply and salary
    p["is_easy_apply"] = bool(re.search(r"Easy Apply", text, re.IGNORECASE))
    p["has_salary"] = bool(re.search(
        r"[£$€]\s*[\d,]+|\d[\d,]+\s*(?:per\s+(?:annum|year|hour)|/\s*(?:yr|hr|year|annum)|\s*a\s+year)",
        text, re.IGNORECASE
    ))

    # Agency signals
    p["is_agency"] = bool(re.search(
        r"\b(?:our client|staffing|recruitment agency|executive search|"
        r"on behalf of our|confidential client|leading (?:global|national|international) company)\b",
        text, re.IGNORECASE
    ))

    # Generic red-flag phrases
    generic_patterns = [
        (r"competitive\s+(?:salary|package|compensation|benefits)", '"Competitive salary": no figure given'),
        (r"fast[- ]?paced\s+(?:environment|team|company|startup|role)", '"Fast-paced environment"'),
        (r"dynamic\s+(?:team|environment|company|organisation)", '"Dynamic team"'),
        (r"passionate\s+about", '"Passionate about"'),
        (r"self[- ]?starter", '"Self-starter"'),
        (r"wear(?:ing)?\s+many\s+hats", '"Wear many hats"'),
        (r"results[- ]?driven", '"Results-driven"'),
        (r"go[- ]?getter", '"Go-getter"'),
        (r"\b(?:rockstar|rock star|ninja|wizard|guru)\b", "Hyperbolic role descriptor"),
        (r"\bteam player\b", '"Team player"'),
        (r"talent\s+pipeline", "Talent pipeline language"),
        (r"looking to (?:speak|connect|chat) with", "Speculative outreach language"),
        (r"exciting\s+(?:opportunity|role|position)", '"Exciting opportunity"'),
        (r"join our (?:growing|expanding|talented|award-?winning)", '"Join our growing team"'),
        (r"proven\s+track\s+record", '"Proven track record"'),
        (r"strong\s+communication\s+skills", '"Strong communication skills"'),
        (r"detail[- ]?oriented", '"Detail-oriented"'),
        (r"hit\s+the\s+ground\s+running", '"Hit the ground running"'),
        (r"can-do\s+attitude", '"Can-do attitude"'),
        (r"passion(?:ate)?\s+for\s+(?:what we do|our mission|excellence)", "Passion-for-mission filler"),
    ]
    p["generic_phrases"] = [
        label for pattern, label in generic_patterns
        if re.search(pattern, text, re.IGNORECASE)
    ]

    # Specificity green flags
    specificity_patterns = [
        (r"reports?\s+(?:to|into)\s+(?:the\s+)?[A-Z]", "Reporting line or line manager mentioned"),
        (r"[£$€][\d,]+(?:\s*[-–]\s*[£$€]?[\d,]+)?", "Specific salary figure or range given"),
        (r"\b(?:Slack|Jira|Salesforce|HubSpot|Figma|React|Python|AWS|Azure|GCP|"
         r"Tableau|Snowflake|Kubernetes|TypeScript|Terraform|Notion)\b",
         "Specific tools or technologies named"),
        (r"interview\s+process|stages?\s+of\s+interview|hiring\s+process",
         "Interview or hiring process described"),
        (r"(?:Head|Director|VP|Chief|Lead|Manager)\s+of\s+[A-Z]",
         "Named internal title or contact mentioned"),
        (r"\b\d+\s+years?\s+(?:of\s+)?experience\b", "Specific experience requirement stated"),
        (r"start(?:ing)?\s+(?:date|salary|in\s+\w+\s+\d{4})", "Specific start details mentioned"),
    ]
    p["specificity_signals"] = [
        label for pattern, label in specificity_patterns
        if re.search(pattern, text)
    ]

    # Description word count (try to isolate "About the job" section)
    about_m = re.search(
        r"About\s+the\s+[Jj]ob\s*([\s\S]*?)"
        r"(?:About\s+the\s+[Cc]ompany|Show\s+(?:more|less)|Skills|Qualifications|$)",
        text, re.IGNORECASE
    )
    desc_text = about_m.group(1).strip() if about_m else text
    p["description_text"] = desc_text
    p["description_word_count"] = len(desc_text.split())

    return p


# ---------------------------------------------------------------------------
# Scorer: five weighted factors returning a 0-100 ghost likelihood score
# ---------------------------------------------------------------------------

def score_listing(p: dict) -> dict:
    """Score a parsed listing across five factors. Returns full result dict."""
    factors = []
    wc = p.get("description_word_count", 0)

    # Factor 1: Posting age and history (weight 30%)
    ps, pf = 0, []
    days = p.get("days_posted")
    if days is not None:
        if   days <= 7:  ps = 0;  pf.append(f"Posted {days} day(s) ago, within normal range")
        elif days <= 14: ps = 2;  pf.append(f"Posted {days} days ago, slightly extended")
        elif days <= 30: ps = 5;  pf.append(f"Posted {days} days ago, a prolonged posting period")
        elif days <= 60: ps = 7;  pf.append(f"Posted {days} days ago, abnormally long")
        else:            ps = 9;  pf.append(f"Posted {days} days ago, a very suspicious duration")
        if p.get("is_reposted"):
            ps = min(10, ps + 4)
            pf.append("Marked REPOSTED by LinkedIn: role was previously closed and relisted")
    else:
        ps = 2
        pf.append("Posting date not detected: try including more of the page text")
    factors.append({
        "name": "Posting age and history",
        "score": min(10, ps),
        "verdict": "red_flag" if ps >= 6 else "caution" if ps >= 3 else "ok",
        "summary": pf[0],
        "details": pf,
    })

    # Factor 2: Description quality (weight 25%)
    ds, df = 0, []
    if   wc < 100: ds += 5; df.append(f"Very short description ({wc} words): genuine roles typically include much more detail")
    elif wc < 200: ds += 3; df.append(f"Brief description ({wc} words), limited detail provided")
    elif wc < 350: ds += 1; df.append(f"Moderate description length ({wc} words)")
    else:                   df.append(f"Detailed description ({wc} words), a positive signal")

    gc = len(p.get("generic_phrases", []))
    if   gc >= 5: ds += 4; df.append(f"{gc} generic template phrases detected, a significant concern")
    elif gc >= 3: ds += 2; df.append(f"{gc} generic filler phrases found")
    elif gc == 1: ds += 1; df.append("1 minor generic phrase found")
    else:                   df.append("No generic filler phrases detected")

    sc = len(p.get("specificity_signals", []))
    if sc > 0:
        ds = max(0, ds - sc)
        df.append(f"{sc} specific detail(s) found, a positive signal")

    dsc = min(10, ds)
    factors.append({
        "name": "Description quality",
        "score": dsc,
        "verdict": "red_flag" if dsc >= 6 else "caution" if dsc >= 3 else "ok",
        "summary": df[0],
        "details": df,
    })

    # Factor 3: Salary and location transparency (weight 20%)
    ts, tf = 0, []
    if not p.get("has_salary"):
        ts += 5; tf.append("No salary or salary range given, a significant transparency concern")
    else:
        tf.append("Salary or salary range is stated, a positive signal")
    if not p.get("work_type"):
        ts += 2; tf.append("Work arrangement (remote/hybrid/on-site) not specified")
    else:
        tf.append(f"Work type stated: {p['work_type']}")
    factors.append({
        "name": "Salary and location transparency",
        "score": min(10, ts),
        "verdict": "red_flag" if ts >= 6 else "caution" if ts >= 3 else "ok",
        "summary": tf[0],
        "details": tf,
    })

    # Factor 4: Posting specificity and intent (weight 15%)
    as_, af = 0, []
    if p.get("is_agency"):
        if wc < 150 or gc >= 4 or (not p.get("has_salary") and wc < 200):
            as_ = 6
            af.append(
                "Agency posting with significant vagueness: limited detail raises the "
                "likelihood this is speculative roster-building rather than a live brief"
            )
        elif wc < 250 or gc >= 2 or not p.get("has_salary"):
            as_ = 3
            af.append(
                "Agency posting with some gaps in detail: a more specific posting with "
                "salary and full responsibilities would reduce this concern"
            )
        else:
            as_ = 1
            af.append(
                "Agency posting with a clear, detailed brief: the level of specificity "
                "suggests this is a live role rather than speculative outreach"
            )
    else:
        af.append("Posted directly by the employer")

    if p.get("is_easy_apply") and (gc >= 3 or wc < 200):
        as_ += 2
        af.append(
            "Easy Apply combined with a vague description: a common pattern for "
            "speculative CV collection"
        )
    elif not p.get("is_easy_apply"):
        af.append("External application process suggests a structured recruitment approach")

    factors.append({
        "name": "Posting specificity and intent",
        "score": min(10, as_),
        "verdict": "red_flag" if as_ >= 6 else "caution" if as_ >= 3 else "ok",
        "summary": af[0],
        "details": af,
    })

    # Factor 5: LinkedIn engagement signals (weight 10%)
    ls, lf = 0, []
    days = p.get("days_posted")
    ac   = p.get("applicant_count")
    if days is not None and ac is not None:
        apd = ac / max(1, days)
        if p.get("is_early_applicant") and days > 14:
            ls += 4; lf.append(f'"Be an early applicant" after {days} days, unusually low engagement')
        elif apd < 0.5 and days > 21:
            ls += 3; lf.append(f"Low engagement: only {ac} applicant(s) over {days} days")
        elif ac > 100 and days <= 14:
            ls = max(0, ls - 1); lf.append(f"Strong interest: {ac}+ applicants in {days} days")
        elif p.get("applicant_label"):
            lf.append(f"Applicant count: {p['applicant_label']}")
    else:
        ls += 1; lf.append("Applicant count not detected: try including more page text")

    if not p.get("company_size_label"):
        ls += 2; lf.append("Company size not listed: cannot assess hiring proportionality")
    else:
        lf.append(f"Company size: {p['company_size_label']}")

    factors.append({
        "name": "LinkedIn engagement signals",
        "score": min(10, ls),
        "verdict": "red_flag" if ls >= 6 else "caution" if ls >= 3 else "ok",
        "summary": lf[0],
        "details": lf,
    })

    # Weighted overall score
    weights = [0.30, 0.25, 0.20, 0.15, 0.10]
    weighted = sum(f["score"] * w for f, w in zip(factors, weights))
    pct = min(100, round(weighted * 10))

    # Traffic light verdict
    if   pct <= 25: verdict = "Looks genuine"
    elif pct <= 60: verdict = "Worth a closer look"
    else:           verdict = "Likely a ghost job"

    # Summary sentence
    if   pct >= 61: summary = "Multiple ghost job signals detected. Think carefully before investing time in a full application."
    elif pct >= 26: summary = "Some concerns detected. Worth doing a few extra checks before applying, but nothing conclusive on its own."
    else:           summary = "This listing shows few signs of being a ghost job. It appears to be a genuine, active vacancy."

    # Red flags and green signals
    red_flags, green_signals = [], []
    if p.get("is_reposted"):
        red_flags.append("LinkedIn explicitly marks this listing as REPOSTED")
    if not p.get("has_salary"):
        red_flags.append("No salary or salary range disclosed")
    if p.get("days_posted", 0) > 30:
        red_flags.append(f"Role has been open for over {p['days_posted']} days")
    if p.get("is_agency") and (wc < 200 or gc >= 3):
        red_flags.append("Agency posting with significant vagueness: limited detail raises the risk this is speculative")
    if gc >= 4:
        red_flags.append(f"{gc} generic template phrases in the description")
    if 0 < wc < 150:
        red_flags.append(f"Unusually short job description ({wc} words)")
    if p.get("is_easy_apply") and gc >= 3:
        red_flags.append("Easy Apply with a vague description: a common pattern for speculative CV collection")

    if p.get("has_salary"):
        green_signals.append("Salary or salary range clearly stated")
    for sig in p.get("specificity_signals", []):
        green_signals.append(sig)
    if not p.get("is_reposted") and p.get("days_posted") is not None and p["days_posted"] <= 10:
        green_signals.append(f"Recently posted ({p['days_posted']} day(s) ago)")
    if p.get("applicant_count", 0) > 50 and p.get("days_posted", 999) <= 14:
        green_signals.append(f"Strong applicant interest: {p['applicant_count']}+ applicants in {p['days_posted']} days")
    if not p.get("is_agency"):
        green_signals.append("Posted directly by the employer")
    elif wc >= 250 and gc < 2:
        green_signals.append("Agency posting with a clear, detailed brief: suggests a live, active role")
    if wc >= 400:
        green_signals.append(f"Detailed job description ({wc} words)")
    if not p.get("is_easy_apply"):
        green_signals.append("External application process suggests structured recruitment")

    # Recommended actions
    actions = []
    if p.get("is_reposted"):
        actions.append(
            "This listing is marked as reposted. Contact the company directly to confirm "
            "the role is actively being filled before applying."
        )
    if not p.get("has_salary"):
        actions.append(
            "Ask for a salary range before submitting a full application. "
            "Legitimate roles should be able to provide one."
        )
    if p.get("days_posted", 0) > 30:
        actions.append(
            f"This role has been open for over {p['days_posted']} days. Find someone at "
            "the company on LinkedIn and reach out to confirm it is still live."
        )
    if p.get("is_agency") and (wc < 250 or gc >= 2):
        actions.append(
            "Ask the recruiter to provide the client company name, a salary range, and "
            "confirmation this is an active live brief rather than a speculative approach."
        )
    actions.append(
        "Search the job title and company name on LinkedIn to check if this role has been "
        "posted multiple times."
    )
    actions.append(
        "Visit the company LinkedIn page to see how many other roles they currently have open."
    )
    if gc >= 3:
        actions.append(
            "The description uses many generic phrases. Try to find a specific team or named "
            "contact before investing time in a full application."
        )

    cannot = [
        "How many times this role has been posted previously (search the title and company name on LinkedIn)",
        "Whether the company has secured recent funding or announced expansion (search their name on Google News)",
        "How many other roles this company currently has open relative to its headcount (check their LinkedIn company page)",
    ]

    return {
        "factors": factors,
        "pct": pct,
        "verdict": verdict,
        "summary": summary,
        "red_flags": red_flags,
        "green_signals": green_signals,
        "generic_phrases": p.get("generic_phrases", []),
        "specificity_signals": p.get("specificity_signals", []),
        "actions": actions,
        "cannot": cannot,
        "parsed": p,
    }


# ---------------------------------------------------------------------------
# Company news search (requires feedparser)
# ---------------------------------------------------------------------------

POSITIVE_SIGNALS = [
    "funding", "investment", "growth", "expansion", "revenue", "profit",
    "raises", "series a", "series b", "series c", "ipo", "acquisition",
    "partnership", "record", "milestone", "launches", "wins", "contract",
    "award", "hiring", "new office",
]
NEGATIVE_SIGNALS = [
    "layoffs", "redundancies", "closure", "bankrupt", "liquidation",
    "downsizing", "restructuring", "losses", "decline", "investigation",
    "fraud", "scandal", "job cuts", "freeze", "paused hiring",
]


def search_company_news(company_name: str) -> tuple:
    """Search Google News RSS for recent signals about the company."""
    if not HAS_FEEDPARSER or not company_name:
        return [], "unavailable"

    query   = f'"{company_name}" (funding OR growth OR layoffs OR expansion OR profit OR hiring)'
    encoded = urllib.parse.quote(query)
    url     = f"https://news.google.com/rss/search?q={encoded}&hl=en-GB&gl=GB&ceid=GB:en"

    try:
        feed = feedparser.parse(url)
    except Exception:
        return [], "unavailable"

    articles, pos_w, neg_w = [], 0, 0
    cutoff     = datetime.now() - timedelta(days=90)
    name_lower = company_name.lower()

    for entry in feed.entries[:25]:
        title   = entry.get("title",   "").lower()
        summary = entry.get("summary", "").lower()
        text    = title + " " + summary
        if name_lower not in text:
            continue

        pub_date = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                pub_date = datetime(*entry.published_parsed[:6])
            except Exception:
                pass

        is_recent = pub_date and pub_date > cutoff
        pos_hits  = [k for k in POSITIVE_SIGNALS if k in text]
        neg_hits  = [k for k in NEGATIVE_SIGNALS if k in text]
        if not (pos_hits or neg_hits):
            continue

        articles.append({
            "title":            entry.get("title", "(no title)"),
            "link":             entry.get("link", ""),
            "date":             pub_date,
            "positive_signals": pos_hits,
            "negative_signals": neg_hits,
            "is_recent":        is_recent,
        })
        m = 2 if is_recent else 1
        pos_w += len(pos_hits) * m
        neg_w += len(neg_hits) * m

    if not articles:
        return [], "no_news"
    if pos_w > neg_w: return articles, "positive"
    if neg_w > pos_w: return articles, "negative"
    return articles, "mixed"


# ---------------------------------------------------------------------------
# Report renderer
# ---------------------------------------------------------------------------

VERDICT_COLOUR = {
    "Looks genuine":        GREEN,
    "Worth a closer look":  AMBER,
    "Likely a ghost job":   RED,
}
FACTOR_COLOUR = {
    "ok":       GREEN,
    "caution":  AMBER,
    "red_flag": RED,
}


def rule(char: str = "─", width: int = 66) -> None:
    print(f"{DIM}{char * width}{RESET}")


def print_report(result: dict, articles: list, news_verdict: str) -> None:
    p       = result["parsed"]
    pct     = result["pct"]
    verdict = result["verdict"]
    colour  = VERDICT_COLOUR.get(verdict, AMBER)

    print(f"\n{BOLD}{BLUE}{'═' * 66}{RESET}")
    print(f"{BOLD}{BLUE}  GHOST JOB DETECTOR — RESULTS{RESET}")
    print(f"{BOLD}{BLUE}{'═' * 66}{RESET}\n")

    # Verdict
    print(f"  {BOLD}Ghost likelihood:{RESET}  {colour}{BOLD}{pct}%{RESET}")
    print(f"  {BOLD}Verdict:{RESET}           {colour}{BOLD}{verdict}{RESET}")
    print(f"\n  {result['summary']}\n")

    # Detected metadata
    print(f"{BOLD}DETECTED FROM LISTING{RESET}\n")
    rule()
    meta = []
    if p.get("post_label"):     meta.append(("Posting status",  p["post_label"], RED if p.get("is_reposted") else None))
    if p.get("applicant_label"): meta.append(("Applicants",     p["applicant_label"], None))
    if p.get("company_size_label"): meta.append(("Company size", p["company_size_label"], None))
    if p.get("work_type"):      meta.append(("Work type",       p["work_type"], None))
    meta.append(("Salary shown",     "Yes" if p.get("has_salary") else "No",
                  GREEN if p.get("has_salary") else ORANGE))
    meta.append(("Easy Apply",       "Yes" if p.get("is_easy_apply") else "No", None))
    meta.append(("Direct employer",  "Via agency" if p.get("is_agency") else "Yes",
                  None if p.get("is_agency") else GREEN))
    for label, value, col in meta:
        val_str = f"{col}{value}{RESET}" if col else value
        print(f"  {DIM}{label:<22}{RESET}{val_str}")

    # Factor breakdown
    print(f"\n{BOLD}FACTOR BREAKDOWN{RESET}\n")
    rule()
    for f in result["factors"]:
        c = FACTOR_COLOUR.get(f["verdict"], AMBER)
        bar_fill = "█" * f["score"] + "░" * (10 - f["score"])
        print(f"\n  {BOLD}{f['name']:<34}{RESET} {c}{f['score']:>2}/10{RESET}  {c}{bar_fill}{RESET}")
        print(f"  {DIM}{f['summary']}{RESET}")

    # Red flags
    if result["red_flags"]:
        print(f"\n\n{BOLD}{RED}RED FLAGS{RESET}\n")
        rule()
        for flag in result["red_flags"]:
            print(f"  {RED}⚠{RESET}  {flag}")

    # Green signals
    if result["green_signals"]:
        print(f"\n\n{BOLD}{GREEN}POSITIVE SIGNALS{RESET}\n")
        rule()
        for sig in result["green_signals"]:
            print(f"  {GREEN}✓{RESET}  {sig}")

    # Generic phrases
    if result["generic_phrases"]:
        print(f"\n\n{BOLD}{AMBER}GENERIC TEMPLATE PHRASES DETECTED{RESET}\n")
        rule()
        for phrase in result["generic_phrases"]:
            print(f"  {AMBER}·{RESET}  {phrase}")

    # Company news
    print(f"\n\n{BOLD}COMPANY NEWS (last 90 days){RESET}\n")
    rule()
    if articles:
        for a in articles[:6]:
            date_str = a["date"].strftime("%d %b %Y") if a.get("date") else "Unknown"
            sigs = a["positive_signals"] + a["negative_signals"]
            sig_str = f"  [{', '.join(sigs)}]" if sigs else ""
            print(f"  {DIM}[{date_str}]{RESET}  {a['title']}{DIM}{sig_str}{RESET}")
    elif news_verdict == "no_news":
        print(f"  {AMBER}No relevant company news found in the last 90 days.{RESET}")
        print(f"  {DIM}Companies actively growing almost always publicise it.{RESET}")
    elif news_verdict == "unavailable":
        print(f"  {DIM}News search unavailable. Install feedparser to enable:{RESET}")
        print(f"  {DIM}  pip install feedparser{RESET}")

    # Recommended actions
    print(f"\n\n{BOLD}RECOMMENDED ACTIONS{RESET}\n")
    rule()
    for i, action in enumerate(result["actions"], 1):
        print(f"  {DIM}{i:02d}{RESET}  {action}")

    # Requires additional research
    print(f"\n\n{BOLD}{DIM}REQUIRES ADDITIONAL RESEARCH{RESET}\n")
    rule()
    for item in result["cannot"]:
        print(f"  {DIM}○  {item}{RESET}")

    print(f"\n\n{BOLD}{BLUE}{'═' * 66}{RESET}")
    print(
        f"{DIM}  Generated: {datetime.now().strftime('%d %B %Y at %H:%M')}  "
        f"|  Ghost Job Detector v2.0  |  ghostjobdetector.com{RESET}"
    )
    print(f"{BOLD}{BLUE}{'═' * 66}{RESET}\n")


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------

def export_json(result: dict) -> str:
    """Return a JSON-serialisable summary of the result."""
    import json
    p = result["parsed"]
    return json.dumps({
        "ghost_likelihood_pct": result["pct"],
        "verdict":              result["verdict"],
        "summary":              result["summary"],
        "detected": {
            "is_reposted":          p.get("is_reposted"),
            "days_posted":          p.get("days_posted"),
            "applicant_count":      p.get("applicant_count"),
            "company_size_label":   p.get("company_size_label"),
            "work_type":            p.get("work_type"),
            "has_salary":           p.get("has_salary"),
            "is_easy_apply":        p.get("is_easy_apply"),
            "is_agency":            p.get("is_agency"),
            "description_words":    p.get("description_word_count"),
            "generic_phrase_count": len(p.get("generic_phrases", [])),
            "specificity_signals":  len(p.get("specificity_signals", [])),
        },
        "factors": [
            {"name": f["name"], "score": f["score"], "verdict": f["verdict"]}
            for f in result["factors"]
        ],
        "red_flags":        result["red_flags"],
        "green_signals":    result["green_signals"],
        "generic_phrases":  result["generic_phrases"],
        "actions":          result["actions"],
    }, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Ghost Job Detector v2.0 — assess whether a LinkedIn job listing is a ghost job.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ghost_job_detector.py
  python ghost_job_detector.py --json
  python ghost_job_detector.py --file listing.txt
  python ghost_job_detector.py --file listing.txt --json
        """
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON instead of the formatted report"
    )
    parser.add_argument(
        "--file", type=str,
        help="Path to a text file containing the job listing (instead of interactive paste)"
    )
    parser.add_argument(
        "--company", type=str,
        help="Company name for news search (optional override if not detectable from listing)"
    )
    args = parser.parse_args()

    if not args.json:
        print(f"\n{BOLD}{BLUE}{'═' * 66}{RESET}")
        print(f"{BOLD}{BLUE}  GHOST JOB DETECTOR  v2.0  |  LinkedIn Edition{RESET}")
        print(f"{BOLD}{BLUE}  ghostjobdetector.com{RESET}")
        print(f"{BOLD}{BLUE}{'═' * 66}{RESET}\n")

        if not HAS_FEEDPARSER:
            print(
                f"  {AMBER}Note: feedparser is not installed. Company news search is disabled.{RESET}\n"
                f"  {DIM}Install it with: pip install feedparser{RESET}\n"
            )

    # Get listing text
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
    else:
        if not args.json:
            print("  Paste the full LinkedIn job listing below.")
            print("  Include everything visible on the page for the best result.")
            print("  When finished, press Enter twice (or Ctrl+D on Mac/Linux).\n")

        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
                if len(lines) >= 2 and lines[-1] == "" and lines[-2] == "":
                    break
        except EOFError:
            pass

        text = "\n".join(lines).strip()

    if len(text) < 80:
        print(
            "Error: listing text is too short. Please paste more of the job page.",
            file=sys.stderr
        )
        sys.exit(1)

    # Parse and score
    parsed = parse_listing(text)
    result = score_listing(parsed)

    # Company news
    company_name = args.company or ""
    if not company_name and not args.json:
        detected = parsed.get("company_size_label", "")
        print(f"\n  {DIM}Tip: use --company \"Company Name\" to enable news search.{RESET}")

    articles, news_verdict = search_company_news(company_name) if company_name else ([], "unavailable")

    if args.json:
        print(export_json(result))
    else:
        print_report(result, articles, news_verdict)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {AMBER}Assessment cancelled.{RESET}\n")
        sys.exit(0)
