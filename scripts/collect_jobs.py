
import json
import re
import hashlib
import urllib.request
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlparse

from googlenewsdecoder import gnewsdecoder


ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.json"
JOBS_FILE = ROOT / "jobs.json"

USER_AGENT = "Mozilla/5.0 CAArticleshipHub/5.0"


RECRUITMENT_TERMS = [
    "vacancy", "vacancies", "hiring", "opening", "openings",
    "recruitment", "required", "requirement", "job", "jobs",
    "career", "careers", "walk-in", "walk in", "looking for"
]

EXCLUDE_TERMS = [
    "exam result", "question paper", "study material",
    "mock test", "admit card", "syllabus",
    "how to become", "registration process",
    "course details", "stipend rules"
]

ARTICLESIP_TERMS = [
    "articleship", "article trainee",
    "article assistant", "ca articles",
    "articles required", "articles wanted"
]


CITY_ALIASES = {
    "Bengaluru": ["bengaluru", "bangalore"],
    "Mumbai": ["mumbai"],
    "Delhi": ["delhi", "new delhi"],
    "Noida": ["noida"],
    "Gurugram": ["gurugram", "gurgaon"],
    "Ghaziabad": ["ghaziabad"],
    "Faridabad": ["faridabad"],
    "Chennai": ["chennai"],
    "Hyderabad": ["hyderabad"],
    "Pune": ["pune"],
    "Kolkata": ["kolkata"],
    "Ahmedabad": ["ahmedabad"],
    "Jaipur": ["jaipur"],
    "Lucknow": ["lucknow"],
    "Indore": ["indore"],
    "Surat": ["surat"],
    "Nagpur": ["nagpur"],
    "Mysuru": ["mysuru", "mysore"],
    "Mangalore": ["mangalore", "mangaluru"],
    "Kochi": ["kochi", "cochin"],
    "Kannur": ["kannur"],
    "Kozhikode": ["kozhikode", "calicut"],
    "Thrissur": ["thrissur"],
    "Coimbatore": ["coimbatore"],
    "Thiruvananthapuram": ["thiruvananthapuram", "trivandrum"],
    "Borivali": ["borivali"],
    "Malad": ["malad"],
    "Thane": ["thane"],
    "Navi Mumbai": ["navi mumbai"],
    "Srinagar": ["srinagar"]
}


def clean(value):
    value = unescape(value or "")
    value = re.sub(
        r"<(script|style).*?>.*?</\1>",
        " ",
        value,
        flags=re.I | re.S
    )
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def recent_date(value):
    if not value:
        return False

    try:
        date = parsedate_to_datetime(value)

        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)

        return now - timedelta(days=180) <= date <= now + timedelta(days=1)

    except Exception:
        return False


def get_text(element, names):
    for child in element:
        tag = child.tag.split("}")[-1]

        if tag in names:
            if child.text:
                return clean(child.text)

            if child.attrib.get("href"):
                return child.attrib["href"]

    return ""


def resolve_link(link):
    """Decode Google News links while retaining the original fallback."""

    if not link.startswith(("https://", "http://")):
        return link

    hostname = urlparse(link).hostname or ""

    if not (
        hostname == "news.google.com"
        or hostname.endswith(".news.google.com")
    ):
        return link

    try:
        result = gnewsdecoder(link, interval=1, timeout=15)

        if (
            isinstance(result, dict)
            and result.get("success")
            and result.get("decoded_url")
        ):
            original_url = result["decoded_url"]

            if original_url.startswith(("https://", "http://")):
                print("Google News link decoded successfully.")
                return original_url

        print("Google News decoder could not extract the original URL.")

    except Exception as error:
        print(f"Google News decoding failed: {error}")

    return link


def find_locations(text):
    text_lower = text.lower()
    found = []

    for city, aliases in CITY_ALIASES.items():
        if any(
            re.search(r"\b" + re.escape(alias) + r"\b", text_lower)
            for alias in aliases
        ):
            found.append(city)

    return found


def extract_stipend(text):
    patterns = [
        r"(?:₹|rs\.?|inr)\s*[\d,]+(?:\s*[-–to]+\s*(?:₹|rs\.?|inr)?\s*[\d,]+)?(?:\s*(?:per month|/month|monthly|p\.m\.))?",
        r"[\d,]+\s*(?:to|[-–])\s*[\d,]+\s*(?:per month|/month|monthly|p\.m\.)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            return clean(match.group(0))

    return ""


def extract_role(text):
    patterns = [
        r"\b(article trainee|article assistant|articleship trainee)\b",
        r"\b(ca articleship|articleship)\b"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            return match.group(0).title()

    return "CA Articleship"


def extract_firm(text):
    """
    Extract firm names using explicit labels and common
    recruitment wording. Avoid guessing when uncertain.
    """

    text = clean(text)

    text = re.sub(
        r"\s*[-|–]\s*LinkedIn.*$",
        "",
        text,
        flags=re.I
    )

    text = text.replace("*", "").replace("_", "")

    stop_pattern = (
        r"\s*(?:📍|🏢|💼|⏳|📌|"
        r"Location\s*:|Role\s*:|Position\s*:|"
        r"Department\s*:|Domain\s*:|"
        r"Qualification\s*:|Eligibility\s*:)"
    )

    patterns = [
        # Explicit firm/company labels.
        r"(?:Firm|Organization|Company Name)\s*:\s*(.{2,100})",

        # Example: Join Pipara & Co LLP and begin your career.
        r"\bJoin\s+(.{2,85}?)(?=\s+(?:and|to)\s+"
        r"(?:build|begin|start|grow)|[.!])",

        # Example: Team at FundTQ.
        r"\b(?:team|position|opportunity)\s+at\s+"
        r"([A-Z][A-Za-z0-9&.'’ -]{2,75}?)"
        r"(?=\s+(?:is|for|in|to)\b|[.,;!])",

        # Example: at Zinzuwadia & Co. is inviting applications.
        r"\bat\s+([A-Z][A-Za-z0-9&.'’ -]{2,75}?)"
        r"(?=\s+is\s+(?:inviting|looking|hiring)|[.,;!])",

        # Names ending in common firm suffixes.
        r"\b([A-Z][A-Za-z0-9&.'’ -]{1,65}?"
        r"(?:&\s*Co\.?|Associates|LLP|Group|"
        r"Private Limited|Pvt\.?\s*Ltd\.?|"
        r"Chartered Accountants))"
        r"(?=\s*[,|–—.]|\s+[A-Z0-9]|\s*$)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if not match:
            continue

        candidate = match.group(1)

        candidate = re.split(
            stop_pattern,
            candidate,
            maxsplit=1,
            flags=re.I
        )[0]

        candidate = re.split(
            r"\s+(?:and build|and begin|and start|"
            r"is inviting|is looking|inviting applications|"
            r"we are looking|we're looking)",
            candidate,
            maxsplit=1,
            flags=re.I
        )[0]

        candidate = candidate.strip(
            " \t-–|:,.!🚨📌🏢*"
        )

        generic = [
            "we are", "we're", "new",
            "new vacancy alert", "vacancy alert",
            "hiring", "ca articleship",
            "article assistant", "article trainee",
            "articleship vacancy"
        ]

        if (
            len(candidate) >= 3
            and len(candidate) <= 85
            and candidate.lower() not in generic
            and not candidate.lower().startswith(
                ("we are ", "we're ", "new vacancy")
            )
        ):
            return candidate

    return "Verify with original source"


def classify(text):
    text = text.lower()

    if re.search(
        r"\b(gst|goods and services tax|indirect tax)\b",
        text
    ):
        return "GST"

    if re.search(
        r"\b(internal audit|statutory audit|tax audit|"
        r"audit and assurance|auditing)\b",
        text
    ):
        return "Audit"

    if re.search(
        r"\b(direct tax|income tax|taxation|"
        r"tax compliance|tax representation)\b",
        text
    ):
        return "Taxation"

    if re.search(
        r"\b(bookkeeping|accounting|accounts department|"
        r"financial accounting)\b",
        text
    ):
        return "Accounts"

    if re.search(
        r"\b(financial management|finance|investment banking)\b",
        text
    ):
        return "Finance"

    return "General Articleship"


def extract_exposure(text):
    text_lower = text.lower()

    departments = {
        "Audit": ["audit", "auditing", "assurance"],
        "Taxation": [
            "taxation", "income tax", "direct tax", "tax audit"
        ],
        "GST": ["gst", "indirect tax"],
        "Accounts": [
            "accounting", "accounts", "bookkeeping"
        ],
        "Finance": [
            "finance", "financial management", "investment banking"
        ],
        "Company Law": [
            "company law", "roc", "corporate law"
        ],
        "Bank Audit": [
            "bank audit", "banking audit"
        ]
    }

    found = []

    for department, keywords in departments.items():
        if any(keyword in text_lower for keyword in keywords):
            found.append(department)

    return found


def extract_summary(description, title):
    summary = clean(description)

    if not summary or summary.lower() == title.lower():
        return "Open the original listing to check vacancy details."

    if len(summary) > 700:
        summary = summary[:697].rsplit(" ", 1)[0] + "..."

    return summary


def make_duplicate_key(job):
    url = job.get("url", "").lower().rstrip("/")

    if url and "news.google.com" not in url:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    title = re.sub(
        r"[^a-z0-9]",
        "",
        job.get("title", "").lower()
    )

    firm = re.sub(
        r"[^a-z0-9]",
        "",
        job.get("firm", "").lower()
    )

    location = ",".join(job.get("locations", []))

    combined = title[:120] + firm + location

    return hashlib.sha256(
        combined.encode("utf-8")
    ).hexdigest()


def fetch_feed(source):
    request = urllib.request.Request(
        source["url"],
        headers={"User-Agent": USER_AGENT}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    items = [
        element for element in root.iter()
        if element.tag.split("}")[-1] in ("item", "entry")
    ]

    print(
        f'{source["name"]}: Raw feed entries = {len(items)}'
    )

    results = []

    for item in items:
        title = get_text(item, ["title"])

        description = get_text(
            item, ["description", "summary", "content"]
        )

        link = get_text(item, ["link"])

        pub_date = get_text(
            item, ["pubDate", "published", "updated"]
        )

        combined = clean(title + " " + description)
        combined_lower = combined.lower()
        title_lower = title.lower()

        if not any(
            term in combined_lower
            for term in ARTICLESIP_TERMS
        ):
            continue

        if not any(
            term in combined_lower
            for term in RECRUITMENT_TERMS
        ):
            continue

        if any(
            term in title_lower
            for term in EXCLUDE_TERMS
        ):
            continue

        if not recent_date(pub_date):
            continue

        if not link.startswith(("https://", "http://")):
            continue

        original_link = resolve_link(link)
        locations = find_locations(combined)
        exposure = extract_exposure(combined)

        job = {
            "id": hashlib.sha256(
                original_link.encode("utf-8")
            ).hexdigest()[:16],

            "title": title,
            "firm": extract_firm(combined),
            "role": extract_role(combined),
            "location": ", ".join(locations) if locations else "Not specified",
            "locations": locations,
            "area": classify(combined),
            "department": exposure,
            "exposure": exposure,
            "stipend": extract_stipend(combined),
            "date": pub_date,
            "summary": extract_summary(description, title),
            "source": source["name"],
            "url": original_link,
            "verification": "Unverified - check original listing"
        }

        results.append(job)

    return results


def main():
    with open(SOURCES_FILE, encoding="utf-8") as file:
        sources = json.load(file)["sources"]

    jobs = {}
    successful = 0
    errors = []

    for source in sources:
        try:
            found = fetch_feed(source)

            for job in found:
                duplicate_key = make_duplicate_key(job)

                if duplicate_key not in jobs:
                    jobs[duplicate_key] = job

            successful += 1

            print(
                f'{source["name"]}: '
                f'{len(found)} possible vacancies'
            )

        except Exception as error:
            errors.append(
                f'{source["name"]}: {error}'
            )

            print(
                f'Feed failed: {source["name"]}: {error}'
            )

    all_jobs = list(jobs.values())

    def sort_date(job):
        try:
            return parsedate_to_datetime(
                job["date"]
            ).timestamp()
        except Exception:
            return 0

    all_jobs.sort(
        key=sort_date,
        reverse=True
    )

    output = {
        "jobs": all_jobs[:500],
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "status": (
            "Collection completed"
            if successful
            else "All feeds failed"
        ),
        "successful_feeds": successful,
        "total_sources": len(sources),
        "feed_errors": errors
    }

    with open(
        JOBS_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(
        f'Total possible vacancies: {len(output["jobs"])}'
    )


if __name__ == "__main__":
    main()
ue

        if not link.startswith(("https://", "http://")):
            continue

        original_link = resolve_link(link)

        locations = find_locations(combined)

        job = {
            "id": hashlib.sha256(
                original_link.encode("utf-8")
            ).hexdigest()[:16],

            "title": title,
            "firm": extract_firm(title),
            "role": extract_role(combined),
            "location": ", ".join(locations) if locations else "Not specified",
            "locations": locations,
            "area": classify(combined),
            "department": extract_exposure(combined),
            "exposure": extract_exposure(combined),
            "stipend": extract_stipend(combined),
            "date": pub_date,
            "summary": extract_summary(description, title),
            "source": source["name"],
            "url": original_link,
            "verification": "Unverified - check original listing"
        }

        results.append(job)

    return results


def main():
    with open(SOURCES_FILE, encoding="utf-8") as file:
        sources = json.load(file)["sources"]

    jobs = {}
    successful = 0
    errors = []

    for source in sources:
        try:
            found = fetch_feed(source)

            for job in found:
                duplicate_key = make_duplicate_key(job)

                if duplicate_key not in jobs:
                    jobs[duplicate_key] = job

            successful += 1

            print(
                f'{source["name"]}: '
                f'{len(found)} possible vacancies'
            )

        except Exception as error:
            errors.append(f'{source["name"]}: {error}')
            print(f'Feed failed: {source["name"]}: {error}')

    all_jobs = list(jobs.values())

    all_jobs.sort(
        key=lambda job: (
            parsedate_to_datetime(job["date"]).timestamp()
            if job.get("date") else 0
        ),
        reverse=True
    )

    output = {
        "jobs": all_jobs[:500],
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "status": "Collection completed" if successful else "All feeds failed",
        "successful_feeds": successful,
        "total_sources": len(sources),
        "feed_errors": errors
    }

    with open(JOBS_FILE, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=2, ensure_ascii=False)

    print(f'Total possible vacancies: {len(output["jobs"])}')


if __name__ == "__main__":
    main()
