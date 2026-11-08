
import json
import re
import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.json"
JOBS_FILE = ROOT / "jobs.json"

RECRUITMENT_TERMS = [
    "articleship vacancy", "articleship opening",
    "articleship openings", "articleship hiring",
    "article trainee vacancy", "article trainee opening",
    "article assistant vacancy", "articles required",
    "articleship recruitment", "ca articles required",
    "ca firm hiring", "chartered accountant articleship vacancy"
]

EXCLUDE_TERMS = [
    "exam", "result", "registration process", "study material",
    "question paper", "syllabus", "mock test", "admit card",
    "stipend rules", "how to become", "eligibility criteria",
    "course details", "notification", "pw"
]

def clean(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(value)).strip()

def recent_date(value):
    if not value:
        return False
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return now - timedelta(days=120) <= date <= now + timedelta(days=1)
    except Exception:
        return False

def classify(text):
    text = text.lower()
    if "audit" in text:
        return "Audit"
    if "gst" in text:
        return "GST"
    if "tax" in text:
        return "Taxation"
    if "account" in text:
        return "Accounts"
    return "Articleship"

def fetch_feed(source):
    request = urllib.request.Request(
        source["url"],
        headers={"User-Agent": "CAArticleshipHub/1.0"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        root = ET.fromstring(response.read())

    results = []

    for item in root.findall(".//item"):
        title = clean(item.findtext("title"))
        link = clean(item.findtext("link"))
        description = clean(item.findtext("description"))
        pub_date = clean(item.findtext("pubDate"))

        title_lower = title.lower()
        combined = (title + " " + description).lower()

        # Recruitment signal must appear in the headline.
        if not any(term in title_lower for term in RECRUITMENT_TERMS):
            continue

        # Reject educational and informational content.
        if any(term in title_lower for term in EXCLUDE_TERMS):
            continue

        if not recent_date(pub_date):
            continue

        if not link.startswith(("https://", "http://")):
            continue

        identifier = hashlib.sha256(
            link.encode("utf-8")
        ).hexdigest()[:16]

        results.append({
            "id": identifier,
            "title": title,
            "firm": "Verify with original source",
            "location": "Not specified",
            "area": classify(combined),
            "stipend": "",
            "date": pub_date,
            "summary": description[:500],
            "source": source["name"],
            "url": link,
            "verification": "Unverified - check original listing"
        })

    return results

def main():
    with open(SOURCES_FILE, encoding="utf-8") as file:
        sources = json.load(file)["sources"]

    # Start fresh so old irrelevant results are removed.
    jobs = {}
    successful = 0
    errors = []

    for source in sources:
        try:
            found = fetch_feed(source)
            for job in found:
                jobs[job["id"]] = job
            successful += 1
            print(f'{source["name"]}: {len(found)} possible vacancies')
        except Exception as error:
            errors.append(f'{source["name"]}: {error}')
            print(f'Feed failed: {source["name"]}: {error}')

    output = {
        "jobs": list(jobs.values())[-500:],
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "status": "Collection completed" if successful else "All feeds failed",
        "successful_feeds": successful,
        "feed_errors": errors
    }

    with open(JOBS_FILE, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=2, ensure_ascii=False)

    print(f'Total possible vacancies: {len(output["jobs"])}')

if __name__ == "__main__":
    main()
    
