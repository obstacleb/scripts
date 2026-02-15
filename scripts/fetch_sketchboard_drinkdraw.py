#!/usr/bin/env python3
import re
import csv
import sys
from datetime import datetime
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

SCHEDULE_URL = "https://www.sketchboard.co/schedule"

HEADERS = [
    "date","venue","title","category","event_type","start_time","end_time",
    "price_text","is_museum","museum_name","event_url","notes"
]

def fetch_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": "artlinks-bot/1.0 (github actions)"})
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")

def parse_date(s: str) -> str:
    # e.g. "Tuesday, February 17, 2026"
    s = s.strip()
    dt = datetime.strptime(s, "%A, %B %d, %Y")
    return dt.strftime("%Y-%m-%d")

def parse_time_range(s: str):
    # e.g. "6:30 PM 8:30 PM" (sometimes has extra spaces)
    s = " ".join(s.split())
    m = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)\s+(\d{1,2}:\d{2}\s*[AP]M)", s, re.I)
    if not m:
        return ("","")
    return (m.group(1).upper().replace(" ", ""), m.group(2).upper().replace(" ", ""))

def is_drink_draw_candidate(title: str, venue_line: str) -> bool:
    t = (title or "").lower()
    v = (venue_line or "").lower()
    # strict + safe: only include Madrone Art Bar sessions
    if "madrone" in t or "madrone" in v:
        return True
    # if Sketchboard later adds literal "Drink & Draw" to titles
    if "drink" in t and "draw" in t:
        return True
    return False

def main():
    html = fetch_html(SCHEDULE_URL)
    soup = BeautifulSoup(html, "html.parser")

    # Each event title is an H1/H2-ish anchor section in the schedule listing.
    # In the HTML text extract we saw patterns like:
    #   # [Title]
    #   * [Day, Month DD, YYYY]
    #   * [Start End]
    #   * [Location...]
    #
    # We’ll find all headings that link to an event page, then look at nearby list items.

    events = []
    for a in soup.select("a"):
        href = a.get("href") or ""
        text = " ".join(a.get_text(" ").split()).strip()
        if not text:
            continue
        # event titles appear as large linked headings; keep only Sketchboard internal links
        if href.startswith("http") and "sketchboard.co" not in href:
            continue
        if href.startswith("/"):
            href = "https://www.sketchboard.co" + href

        # Heuristic: the "View Event →" link is present, but titles are also links.
        # We only want likely “event page” links:
        if "View Event" in text:
            continue
        if "sketchboard.co" not in href:
            continue

        # Look for a nearby parent section that contains bullet list items with date/time
        container = a.find_parent()
        if not container:
            continue

        block_text = container.get_text("\n", strip=True)

        # Must contain a weekday date line like "Tuesday, February 17, 2026"
        date_match = re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}", block_text)
        if not date_match:
            continue

        date_iso = ""
        try:
            date_iso = parse_date(date_match.group(0))
        except Exception:
            continue

        # Time range line like "6:30 PM 8:30 PM"
        start, end = ("","")
        time_match = re.search(r"\d{1,2}:\d{2}\s*[AP]M\s+\d{1,2}:\d{2}\s*[AP]M", block_text, re.I)
        if time_match:
            start, end = parse_time_range(time_match.group(0))

        # Venue line: try to pick something meaningful (often appears after time)
        # We’ll prefer lines that include "Madrone" explicitly.
        venue_line = ""
        for line in block_text.split("\n"):
            if "Madrone" in line or "Madrone" in block_text:
                # keep a concise venue label
                if "Madrone" in line:
                    venue_line = line
                    break

        # Only keep Drink & Draw candidates
        if not is_drink_draw_candidate(text, venue_line):
            continue

        # Hardcode the “Drink & Draw” category; price from the top schedule section can vary,
        # so keep price unknown unless present in block.
        price = ""
        # Sometimes blocks include prices; try to capture "$15" etc
        price_match = re.search(r"\$\d+[^\\n]*", block_text)
        if price_match:
            price = price_match.group(0).strip()

        events.append({
            "date": date_iso,
            "venue": "Sketchboard @ Madrone Art Bar",
            "title": text,
            "category": "Drink & Draw",
            "event_type": "",
            "start_time": start,
            "end_time": end,
            "price_text": price or "$15 CASH ONLY @ the door (per Sketchboard schedule)",
            "is_museum": "no",
            "museum_name": "",
            "event_url": href,
            "notes": "Auto-imported from sketchboard.co/schedule",
        })

    # de-dupe by date+title
    seen = set()
    uniq = []
    for ev in events:
        key = (ev["date"], ev["title"].lower().strip())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(ev)

    # output to stdout as CSV (GitHub Action will write file)
    w = csv.DictWriter(sys.stdout, fieldnames=HEADERS)
    w.writeheader()
    for ev in sorted(uniq, key=lambda x: (x["date"], x["start_time"], x["title"])):
        w.writerow(ev)

if __name__ == "__main__":
    main()
