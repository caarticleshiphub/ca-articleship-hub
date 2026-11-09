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
    "vacancy", "vacancies", "hiring", "opening", "openings",
    "recruitment", "required", "requirement", "job", "jobs",
    "career", "careers", "walk-in", "walk in"
]

EXCLUDE_TERMS = [
    "exam result", "question paper", "study material",
    "mock test", "admit card", "syllabus",
    "how to become", "registration process",
    "course details", "stipend rules"
]

CITIES = [
    "Bengaluru", "Bangalore","Noida","Gurugram","Gurgaon",
    "Ghaziabad","Borivali","Malad","Srinagar","Faridabad",
    "Thane","Navi Mumbai", "Mumbai", "Delhi", "New Delhi",
    "Chennai", "Hyderabad", "Pune", "Kolkata", "Kochi",
    "Cochin", "Kannur", "Calicut", "Kozhikode", "Thrissur",
    "Coimbatore", "Ahmedabad", "Jaipur", "Lucknow", "Indore",
    "Surat", "Nagpur", "Mysuru", "Mangalore", "Thiruvananthapuram"
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
        return now - timedelta(days=180) <= date <= now + timedelta(days=1)
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
    if "account" in text or "bookkeeping" in text:
        return "Accounts"
    return "Articleship"

def find_location(text):
    text_lower = text.lower()
    for city in CITIES:
        if city.lower() in text_lower:
            return city
    return "Not specified"

def get_text(element, names):
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return clean(found.text)

    for child in element:
        if child.tag.split("}")[-1] in names and child.text:
            return clean(child.text)

    return ""

def fetch_feed(source):
    request = urllib.request.Request(
        source["url"],
        headers={"User-Agent": "Mozilla/5.0 CAArticleshipHub/2.0"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

        items = [
        element for element in root.iter()
        if element.tag.split("}")[-1] in ("item", "entry")
    ]

    print(f'{source["name"]}: Raw feed entries = {len(items)}')

    for item in items[:5]:
        title = get_text(item, ["title"])
        pub_date = get_text(item, ["pubDate", "published", "updated"])
        print(f"DEBUG TITLE: {title}")
        print(f"DEBUG DATE: {pub_date}")

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

        # Atom feeds may store the link in an href attribute.
        if not link:
            for child in item:
                if child.tag.split("}")[-1] == "link":
                    link = child.attrib.get("href", "")
                    if link:
                        break

        title_lower = title.lower()
        combined = (title + " " + description).lower()

        # Require articleship-related content.
        if not any(term in combined for term in [
            "articleship", "article trainee",
            "article assistant", "ca articles"
        ]):
            continue

        # Require a recruitment signal in title or description.
        if not any(term in combined for term in RECRUITMENT_TERMS):
            continue

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
            "location": find_location(combined),
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

    jobs = {}
    successful = 0
    errors = []

    for source in sources:
        try:
            found = fetch_feed(source)

                        for job in found:
                duplicate_key = re.sub(
                    r"[^a-z0-9]",
                    "",
                    job["title"].lower()
                )

                duplicate_key = duplicate_key[:100]

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

    output = {
        "jobs": list(jobs.values())[-500:],
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
