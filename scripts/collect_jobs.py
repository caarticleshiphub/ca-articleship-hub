
import json
import re
import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from html import unescape

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.json"
JOBS_FILE = ROOT / "jobs.json"

KEYWORDS = [
    "ca articleship", "articleship vacancy",
    "article trainee", "articles trainee",
    "chartered accountant trainee",
    "ca firm articleship"
]

def clean(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(value)).strip()

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
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    results = []

    for item in root.findall(".//item"):
        title = clean(item.findtext("title"))
        link = clean(item.findtext("link"))
        description = clean(item.findtext("description"))
        pub_date = clean(item.findtext("pubDate"))

        text = (title + " " + description).lower()

        if not any(word in text for word in KEYWORDS):
            continue

        if not link.startswith(("https://", "http://")):
            continue

        identifier = hashlib.sha256(
            link.encode("utf-8")
        ).hexdigest()[:16]

        results.append({
            "id": identifier,
            "title": title,
            "firm": "See original listing",
            "location": "India / Not specified",
            "area": classify(text),
            "stipend": "",
            "date": pub_date,
            "summary": description[:500],
            "source": source["name"],
            "url": link
        })

    return results

def main():
    with open(SOURCES_FILE, encoding="utf-8") as file:
        sources = json.load(file)["sources"]

    try:
        with open(JOBS_FILE, encoding="utf-8") as file:
            old_data = json.load(file)
            old_jobs = old_data.get("jobs", [])
    except (FileNotFoundError, json.JSONDecodeError):
        old_jobs = []

    jobs = {job["id"]: job for job in old_jobs if job.get("id")}
    successful = 0
    errors = []

    for source in sources:
        try:
            found = fetch_feed(source)
            for job in found:
                jobs[job["id"]] = job
            successful += 1
            print(f'{source["name"]}: {len(found)} relevant results')
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

    print(f'Total stored opportunities: {len(output["jobs"])}')

if __name__ == "__main__":
    main()
  
