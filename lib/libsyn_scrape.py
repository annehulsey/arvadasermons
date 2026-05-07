import os
import re
import requests
import json
import time
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

from .paths import SERMONS_PATH

URL_BASE_PAGE = "http://milehighvineyard.libsyn.com/page/{}/size/20"

TITLE_PREFIXES = {"The", "This", "That", "Sunday", "Pastor", "Pator", "Dr"}
SPEAKER_ANCHORS = {"Pastor", "Guest speaker"}
KNOWN_SPEAKERS = {"Dave Donaldson",
                  "Jay Pathak", 
                  "Nicole McAdoo-Popovich",
                  "Noelle Shearer", 
                  "Preston Ulmer", 
                  "Rob Morris",
                  "Rick Love and Imam Shemsadeen"
                  }
FIRST_NAME_SPEAKERS = {"Becca and Jay": "Becca Knudsen and Jay Pathak",
                       "Jay": "Jay Pathak",
                       "Anabeth": "Anabeth Morgan",
                       "Corey": "Corey Garris"
                       }
SPEAKER_MISSPELLINGS = {"batisms, november": "Jay Pathak",
                        "bel folman": "Ben Folman",
                        "becca knusden": "Becca Knudsen",
                        "cory garris": "Corey Garris",
                        'grace you have been saved"': "Jay Pathak",
                        "dr": "Ray Bakke"
                        }

SERIES_MISSPELLINGS = {"Better Choices Better Life": "Better Choices, Better Life"}

FILLER_DESCRIPTION = "Thank you for joining our online service"
FILLER_CHURCH = "Mile High Vineyard"
MAX_SERIES_COUNTER = 20

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



def capitalize(s):
    def repl(match):
        return match.group(1) + match.group(2).upper()

    # capitalize after start OR after space/( /" but NOT after apostrophe
    return re.sub(r'(^|[\s\(\["])([a-z])', repl, s.lower())


def normalize_series(series: str):
    if not series:
        return series

    series = series.replace(":", "").replace(".", "").strip()

    # remove Week or Part
    match = re.search(
        r"(?:week|part)?\s*(\d+)$",
        series,
        flags=re.IGNORECASE
    )

    # remove final N
    if match:
        n = int(match.group(1))

        if n <= MAX_SERIES_COUNTER:
            series = series[:match.start()]

    series = capitalize(series.strip(" -—–:,"))

    series = SERIES_MISSPELLINGS.get(series, series)

    return series


def resolve_description(desc_el):

    description = desc_el.get_text(strip=True) if desc_el else None
    if description and FILLER_DESCRIPTION.lower() in description.lower():
        description = None
    return description


def extract_after_speaker_anchor(desc, anchors):
    for anchor_word in anchors:
        anchor = re.search(
            rf"\b{re.escape(anchor_word)}\b[\s,]+",
            desc,
            flags=re.IGNORECASE
        )

        if anchor:
            start = anchor.end()
            segment = desc[start:].lstrip(" ,.-")

            match = re.match(
                r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                segment
            )

            if match:
                return match.group(1).strip()

    return None

def resolve_known_speaker(desc: str):
    if not desc:
        return None

    # normalize whitespace once
    desc = re.sub(r"\s+", " ", desc).strip()

    # --- 1. full known speaker match ---
    for name in KNOWN_SPEAKERS:
        if re.search(rf"\b{re.escape(name)}\b", desc):
            return name

    # --- 2. alias / first-name mappings ---
    for alias, full_name in FIRST_NAME_SPEAKERS.items():
        if re.search(rf"\b{re.escape(alias)}\b", desc):
            return full_name

    # --- 3. fallback: single-word alias match (very weak) ---
    words = desc.split()
    if words:
        first = words[0].rstrip(",.:;")

        if first in FIRST_NAME_SPEAKERS:
            return FIRST_NAME_SPEAKERS[first]

    return None

def fix_speaker_spelling(speaker: str):
    if not speaker:
        return speaker

    speaker_clean = " ".join(speaker.split()).strip()

    return SPEAKER_MISSPELLINGS.get(speaker_clean.lower(), speaker_clean)


def infer_speaker(speaker, description):
    if speaker is not None:
        return speaker
    
    if not description:
        return '[not available]'
    
    desc = re.sub(r"\s+", " ", description).strip()   
    

    # --- 1. structured anchors (guest speaker / pastor) ---
    name = extract_after_speaker_anchor(desc, SPEAKER_ANCHORS)
    if name:
        return name

    # --- 2. "XXX by <speaker>" OR "by <speaker>" ---
    anchor = re.search(r"\bby\s+", desc, flags=re.IGNORECASE)

    if anchor:
        start = anchor.end()

        match = re.match(
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            desc[start:]
        )
        if match:
            return match.group(1).strip()

    # --- 3. First two words are a capitalized name ---
    words = desc.split()

    # strip leading titles
    while words and words[0].rstrip(".") in TITLE_PREFIXES:
        words = words[1:]

    # now re-evaluate
    if len(words) >= 2:
        first, second = words[0], words[1]

        if first.istitle() and second.istitle():
            return f"{first} {second}"
        

    # --- 4. sweep known speakers ---- 
    speaker = resolve_known_speaker(desc)
    if speaker:
        return speaker

    return '[not available]'


def parse_line_splits(title_splits):

    title_n_splits = len(title_splits)

    series = title_splits[0].lower().strip()
    series = normalize_series(series)

    # remove Mile High Vineyard
    if title_splits[-1]==FILLER_CHURCH:
        title_splits = title_splits[:-1]
    
    if len(title_splits) > 1:
        speaker = title_splits[-1]
        episode_label = " | ".join(title_splits[1:-1])
    else:
        speaker = '[not available]'
        episode_label = None

    return {
        "title_n_splits": title_n_splits,
        "series": series,
        "episode_label": episode_label,
        "speaker": speaker,
    }

def parse_colon_splits(title, description):
    # split off speaker (case-insensitive "by", including "- by")
    parts = re.split(
        r"\s*[-—–]?\s+by\s+",
        title,
        flags=re.IGNORECASE
    )

    if len(parts) > 1:
        main = " by ".join(parts[:-1]).rstrip(" -—–:")
        speaker = parts[-1]
    else:
        main = title
        speaker = None

    parts = re.split(
        r"\s*[-—–]?\s+by\s+",
        title,
        flags=re.IGNORECASE
    )

    if len(parts) > 1:
        main = " by ".join(parts[:-1]).rstrip(" -—–:")
        speaker = parts[-1]
    else:
        main = title
        speaker = None

    # split series and episode
    if ":" in main:
        series, episode = main.split(":", 1)
    else:
        series, episode = main, None
    series = normalize_series(series)

    speaker = infer_speaker(speaker, description)

    return {
        "title_n_splits": 1,
        "series": series.strip(),
        "episode_label": episode.strip() if episode else None,
        "speaker": speaker.strip() if speaker else None,
    }



def parse_title(item):
    title = item.get("title")
    if not title:
        return {}

    title_splits = [p.strip() for p in title.split("|") if p.strip()]
    title_n_splits = len(title_splits)

    if not title_splits:
        return {}

    if title_n_splits > 1:
        return parse_line_splits(title_splits)
    
    else:
        return parse_colon_splits(title, item.get("description"))



def enrich_metadata(item):
    item.update(parse_title(item))

    # normalize speaker if it exists
    if "speaker" in item:
        item["speaker"] = fix_speaker_spelling(item["speaker"])

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
    SERMONS_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(SERMONS_PATH, "a") as f:
        f.write(json.dumps(ep, ensure_ascii=False) + "\n")

# ----------------------------
# BACKFILL
# ----------------------------
def build_backfill(max_pages=100, max_empty_pages=5):

    seen = set()
    results = []

    empty_streak = 0

    for page in range(1, max_pages + 1):

        soup = fetch_page(page)
        page_sermons = parse_libsyn_page(soup)

        new_count = 0

        for ep in page_sermons:
            key = episode_key(ep)

            if not key or key in seen:
                continue

            seen.add(key)
            append_episode(ep)
            results.append(ep)
            new_count += 1

        print(f"Page {page}: +{new_count} new sermons")

        # --- empty page tracking ---
        if new_count == 0:
            empty_streak += 1
            print(f"Empty page streak: {empty_streak}")

        else:
            empty_streak = 0  # reset if we find anything new

        # --- stop condition ---
        if empty_streak >= max_empty_pages:
            print(f"Hit {max_empty_pages} consecutive empty pages — stopping early")
            break

        time.sleep(0.5)

    print("Backfill complete")
    return results


# ----------------------------
#  LOAD DATASET
# ----------------------------
def load_existing_keys(path=SERMONS_PATH):
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


def update_new_sermons(max_pages=10, max_known_streak=3):
    """
    Incrementally fetch new sermons from Libsyn.

    Safer stopping behavior:
    - Only increments known-page streak if an ENTIRE page is new-free
    - Resets streak immediately when ANY new sermon is found
    - Prevents premature stopping from interleaved ordering
    """

    seen = load_existing_keys()

    print("Checking for new sermons from page 1...")

    consecutive_known_pages = 0
    total_new = 0

    for page in range(1, max_pages + 1):

        soup = fetch_page(page)
        page_sermons = parse_libsyn_page(soup)

        if not page_sermons:
            print(f"Page {page}: no sermons found, stopping")
            break

        new_count = 0

        for ep in page_sermons:
            key = episode_key(ep)

            if not key:
                continue

            if key in seen:
                continue

            # NEW sermon found
            seen.add(key)
            append_episode(ep)
            new_count += 1
            total_new += 1

        # -----------------------------
        # STREAK LOGIC
        # -----------------------------

        if new_count == 0:
            consecutive_known_pages += 1
            print(f"Page {page}: 0 new sermons (known streak = {consecutive_known_pages})")
        else:
            consecutive_known_pages = 0
            print(f"Page {page}: +{new_count} new sermons")

        # Stop only after several FULLY-known pages in a row
        if consecutive_known_pages >= max_known_streak:
            print("Hit known-page streak — stopping early")
            break

        time.sleep(0.5)

    print(f"Update complete: {total_new} new sermons added")

