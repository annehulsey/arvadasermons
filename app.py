import streamlit as st
import pandas as pd
import json
from datetime import datetime

from lib.paths import SERMONS_PATH

DROP_BONUS_EPISODES = True
DROP_DEVOTIONALS = True

# =========================
# DATA LOADING (PLACEHOLDER)
# =========================
@st.cache_data
def load_data():
    data = []
    with open(SERMONS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            data.append(json.loads(line))
    data = pd.DataFrame(data)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    if DROP_BONUS_EPISODES:
        idx = data['series']=='Bonus Episode'
        data = data[~idx]
    if DROP_DEVOTIONALS:
        data = data[~data['series'].str.contains("devotion", case=False, na=False)]
    return data

df = load_data()



# =========================
# STATE
# =========================
if "view" not in st.session_state:
    st.session_state.view = "list"
if "sort_newest" not in st.session_state:
    st.session_state.sort_newest = True
if "page" not in st.session_state:
    st.session_state.page = 1
if "series_page" not in st.session_state:
    st.session_state.series_page = 1

PAGE_SIZE = 10
SERIES_PAGE_SIZE = 30

# =========================
# HEADER
# =========================
st.title("Arvada Vineyard — Sermon Catalogue")

st.divider()

# =========================
# STATS
# =========================
col1, col2, col3, col4 = st.columns(4)

print(df.columns)
col1.metric("Sermons", len(df))
col2.metric("Series", df["series"].nunique())
col3.metric("Study Guides", 0)


# =========================
# FILTERING
# =========================
st.subheader("Filtering")

search = st.text_input("Search title, speaker, description, series")

years = sorted(df["year"].dropna().unique())
year_filter = st.selectbox("Year", ["All"] + list(years))

speakers = sorted(df["speaker"].dropna().unique())
speaker_filter = st.selectbox("Speaker", ["All"] + speakers)

series_list = sorted(df["series"].dropna().unique())
series_filter = st.selectbox("Series", ["All"] + series_list)


filtered = df.copy()

if search:
    filtered = filtered[
        filtered.apply(
            lambda r: search.lower() in str(r).lower(),
            axis=1
        )
    ]

if year_filter != "All":
    filtered = filtered[filtered["year"] == year_filter]

if speaker_filter != "All":
    filtered = filtered[filtered["speaker"] == speaker_filter]

if series_filter != "All":
    filtered = filtered[filtered["series"] == series_filter]



# =======================
# SORT AND EXPORT
# =======================
view = st.segmented_control(
    "",
    options=["All sermons", "By series"],
    default="All sermons"
)

st.session_state.view = "list" if view == "All sermons" else "series"

sorting = st.segmented_control(
    "",
    options=["Newest first","Oldest first"],
    default="Newest first"
)

st.session_state.sort_newest = True if sorting == "Newest first" else False


# sorting
filtered = filtered.sort_values(
    by="date",
    ascending = not st.session_state.sort_newest
)


st.session_state.page_count = max(1, (len(filtered) // PAGE_SIZE) + 1)


# ====================
# DOWNLOAD
# ====================
default_name = "sermons.csv"

filename = st.text_input("Filename", value=default_name)

# ensure it's never empty and always ends with .csv
filename = (filename or default_name).strip()
if not filename.lower().endswith(".csv"):
    filename += ".csv"

csv = df.to_csv(index=False)

st.download_button(
    label="Download CSV",
    data=csv,
    file_name=filename,
    mime="text/csv"
)

# =========================
# RENDER EPISODE
# =========================

def remove_spaces(s):
    return " ".join(s.split()) if s else s


def render_episode(row):
    with st.container(border=True):

        if row.get("series") and row.get("episode_label"):
            label = f"{row['series']}: {row['episode_label']}"
        elif row.get("series"):
            label = f"{row['series']}"
        st.markdown(f"### {label}")

        if row.get("date"):
            date_str = row["date"].strftime("%B %d, %Y")
            st.caption(f"Upload date: {date_str}")

        if row.get("series"):
            st.markdown(f"**Series:** {row['series']}")

        if row.get("speaker"):
            st.markdown(f"**Speaker:** {row['speaker']}")

        if row.get("title"):
            st.caption(row["title"])

        if row.get("description") and remove_spaces(row["description"])!=remove_spaces(row["title"]):
            st.caption(row["description"])

        if row.get("audio_url"):
            st.link_button("▶ Listen", row["audio_url"])

# =========================
# LIST VIEW
# =========================
def render_list_view(data):

    # --------------------------
    # COMPUTE PAGE META FIRST
    # --------------------------
    total_pages = st.session_state.page_count
    start = (st.session_state.page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_data = data.iloc[start:end]

    # --------------------------
    # RENDER CONTENT FIRST
    # --------------------------
    st.write(f"Showing {len(page_data)} of {len(data)}")

    for _, row in page_data.iterrows():
        render_episode(row)

    # --------------------------
    # PAGINATION AT BOTTOM (UI ONLY)
    # --------------------------
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button("Prev", key="prev") and st.session_state.page > 1:
            st.session_state.page -= 1
            st.rerun()

    with col3:
        if st.button("Next", key="next") and st.session_state.page < total_pages:
            st.session_state.page += 1
            st.rerun()

    with col2:
        st.write(f"Page {st.session_state.page} of {total_pages}")

# =========================
# SERIES VIEW
# =========================

def format_date_range(start, end):
    """
    Smart compact date range formatting.
    Assumes start/end are pandas.Timestamp or datetime.
    """

    if start is None or end is None:
        return ""

    start = pd.to_datetime(start)
    end = pd.to_datetime(end)

    # single date
    if start.day == end.day:
        return f"{start.strftime('%B')} {start.day}, {start.year}"

    # same year
    if start.year == end.year:

        # same month
        if start.month == end.month:
            return f"{start.strftime('%B')} {start.day}–{end.day}, {start.year}"

        # different months, same year
        return f"{start.strftime('%B')} {start.day}–{end.strftime('%B')} {end.day}, {start.year}"

    # different years
    return f"{start.strftime('%b %Y')} – {end.strftime('%b %Y')}"


def render_series_view(data):

    series_order = (
        data.groupby("series")["date"]
        .max()
        .sort_values(ascending=not st.session_state.sort_newest)
        .index
    )
    series_list = list(series_order)

    max_series_pages = max(1, (len(series_list) - 1) // SERIES_PAGE_SIZE + 1)

    # clamp page
    st.session_state.series_page = max(
        1,
        min(st.session_state.series_page, max_series_pages)
    )

    # compute slice
    start = (st.session_state.series_page - 1) * SERIES_PAGE_SIZE
    end = start + SERIES_PAGE_SIZE
    page_series = series_list[start:end]

    st.write(f"Showing {len(page_series)} of {len(series_list)}")

    # render
    for series_name in page_series:
        if not series_name:
            continue

        group = data[data["series"] == series_name]

        group = group.sort_values(
            by="date",
            ascending=not st.session_state.sort_newest
        )

        start_date = group["date"].min()
        end_date = group["date"].max()
        date_range = format_date_range(start_date, end_date)

        group_label = (
            f"{series_name} ({len(group)})"
            f"    |    {date_range}"
        )

        with st.expander(group_label):
            st.markdown("### Sermons")
            for _, row in group.iterrows():
                render_episode(row)

    # pagination (NO rerun)
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button("Prev", key="series_prev") and st.session_state.series_page > 1:
            st.session_state.series_page -= 1

    with col3:
        if st.button("Next", key="series_next") and st.session_state.series_page < max_series_pages:
            st.session_state.series_page += 1

    with col2:
        st.write(f"Page {st.session_state.series_page} of {max_series_pages}")

# =========================
# RENDER
# =========================
st.session_state.page = max(1, min(st.session_state.page, st.session_state.page_count))

if st.session_state.view == "list":
    render_list_view(filtered)
    # reset for next series state
    st.session_state.series_page = 1
else:
    render_series_view(filtered)