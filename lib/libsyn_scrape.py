import os
import re
import requests
import json
import time
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

from .paths import EPISODES_PATH

URL_BASE_PAGE = "http://milehighvineyard.libsyn.com/page/{}/size/20"

FILLER_DESCRIPTION = "Thank you for joining our online service"

# ----------------------------
# PAGE SCRAPING
# ----------------------------
def fetch_page(page_num, retries=2):
    url = URL_BASE_PAGE.format(page_num)

    for i in range(retries):
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2)


def normalize_series(series: str):
    if not series:
        return series

    parts = series.strip().split()

    # check if last token is an integer
    if parts and parts[-1].isdigit():
        return " ".join(parts[:-1])

    return series.title()


def resolve_description(desc_el):

    description = desc_el.get_text(strip=True) if desc_el else None
    if description and FILLER_DESCRIPTION.lower() in description.lower():
        description = None
    return description



def parse_title(title):
    if not title:
        return {}

    title_splits = [p.strip() for p in title.split("|") if p.strip()]

    if not title_splits:
        return {}

    series = title_splits[0].lower().strip()
    series = normalize_series(series)

    has_full_structure = len(title_splits) >= 4

    church = title_splits[-1] if has_full_structure else None
    speaker = title_splits[-2] if has_full_structure else None

    if has_full_structure:
        episode_label = " | ".join(title_splits[1:-2])
    else:
        episode_label = " | ".join(title_splits[1:]) if len(title_splits) > 1 else None

    return {
        "title_n_splits": len(title_splits),
        "series": series,
        "episode_label": episode_label,
        "speaker": speaker,
        "church": church,
    }


def enrich_metadata(item):
    item.update(parse_title(item.get("title")))
    return item


def parse_libsyn_page(soup):

    episodes = []

    rows = soup.find_all("tr")

    for row in rows:
        date_el = row.select_one(".postDate")
        title_el = row.select_one("a.postTitle")
        desc_el = row.select_one(".postBody p")
        details = row.select_one(".postDetails")
        iframe = row.select_one("iframe")

        if not title_el or not details:
            continue

        # title + episode page
        title = title_el.get_text(strip=True)
        episode_page = title_el.get("href")

        # date
        date = date_el.get_text(strip=True) if date_el else None
        try:
            dt = datetime.strptime(date, "%a, %d %B %Y")
            date = dt.date().isoformat()
            year = dt.year
        except Exception:
            date = None
            year = None

        # audio url
        audio_url = None
        audio_url_a = details.find("a", href=re.compile(r"traffic\.libsyn\.com"))
        if audio_url_a:
            audio_url = audio_url_a["href"]

        # episode id
        episode_id = None
        if iframe and iframe.get("src"):
            m = re.search(r"episode/id/(\d+)", iframe["src"])
            if m:
                episode_id = m.group(1)

        # dest id
        dest_id = None
        if iframe and iframe.get("src"):
            m = re.search(r"tdest_id/(\d+)", iframe["src"])
            if m:
                dest_id = m.group(1)

        # category
        category = None
        cat_a = details.find("a", href=re.compile(r"/webpage/category/"))
        if cat_a:
            category = cat_a.get_text(strip=True)

        # description
        description = resolve_description(desc_el)

        episode_dict = {
            "date": date,
            "year": year,
            "title": title,
            "episode_page": episode_page,
            "audio_url": audio_url,
            "episode_id": episode_id,
            "dest_id": dest_id,
            "category": category,
            "description": description
        }

        enrich_metadata(episode_dict)

        episodes.append(episode_dict)

    return episodes



# DEDUPE KEY
# ----------------------------

def episode_key(ep):
    key = (
        ep.get("episode_id"),
        ep.get("dest_id"),
        ep.get("audio_url"),
    )
    if not any(key):
        return None
    return key

# APPEND ONLY STORAGE
# ----------------------------
def append_episode(ep):
    EPISODES_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(EPISODES_PATH, "a") as f:
        f.write(json.dumps(ep, ensure_ascii=False) + "\n")

# ----------------------------
# BACKFILL
# ----------------------------
def build_backfill(max_pages=100):

    seen = set()
    results = []

    for page in range(1, max_pages + 1):

        soup = fetch_page(page)
        page_episodes = parse_libsyn_page(soup)

        new_count = 0

        for ep in page_episodes:
            key = episode_key(ep)

            if not key or key in seen:
                continue

            seen.add(key)
            append_episode(ep)
            results.append(ep)
            new_count += 1

        print(f"Page {page}: +{new_count} new episodes")

        time.sleep(0.5)

    print("Backfill complete")
    return results


# ----------------------------
#  LOAD DATASET
# ----------------------------
def load_existing_keys(path=EPISODES_PATH):
    seen = set()

    if not os.path.exists(path):
        return seen

    with open(path) as f:
        for line in f:
            try:
                ep = json.loads(line)
            except Exception:
                continue

            key = (ep.get("episode_id"), ep.get("dest_id"), ep.get("audio_url"))

            if any(key):
                seen.add(key)

    return seen


def update_new_episodes(max_pages=10, max_known_streak=3):
    """
    Incrementally fetch new episodes from Libsyn.

    Safer stopping behavior:
    - Only increments known-page streak if an ENTIRE page is new-free
    - Resets streak immediately when ANY new episode is found
    - Prevents premature stopping from interleaved ordering
    """

    seen = load_existing_keys()

    print("Checking for new episodes from page 1...")

    consecutive_known_pages = 0
    total_new = 0

    for page in range(1, max_pages + 1):

        soup = fetch_page(page)
        page_episodes = parse_libsyn_page(soup)

        if not page_episodes:
            print(f"Page {page}: no episodes found, stopping")
            break

        new_count = 0

        for ep in page_episodes:
            key = episode_key(ep)

            if not key:
                continue

            if key in seen:
                continue

            # NEW episode found
            seen.add(key)
            append_episode(ep)
            new_count += 1
            total_new += 1

        # -----------------------------
        # STREAK LOGIC
        # -----------------------------

        if new_count == 0:
            consecutive_known_pages += 1
            print(f"Page {page}: 0 new episodes (known streak = {consecutive_known_pages})")
        else:
            consecutive_known_pages = 0
            print(f"Page {page}: +{new_count} new episodes")

        # Stop only after several FULLY-known pages in a row
        if consecutive_known_pages >= max_known_streak:
            print("Hit known-page streak — stopping early")
            break

        time.sleep(0.5)

    print(f"Update complete: {total_new} new episodes added")

