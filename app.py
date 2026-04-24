import streamlit as st
import pandas as pd
import json
from datetime import datetime

from lib.paths import EPISODES_PATH

DROP_BONUS_EPISODES = True

# =========================
# DATA LOADING (PLACEHOLDER)
# =========================
@st.cache_data
def load_data():
    data = []
    with open(EPISODES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            data.append(json.loads(line))
    data = pd.DataFrame(data)
    if DROP_BONUS_EPISODES:
        idx = data['series']=='Bonus Episode'
        data = data[~idx]
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

PAGE_SIZE = 30


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
col4.metric("Showing", 0)  # updated later


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


# sorting
filtered = filtered.sort_values(
    by="year",
    ascending=not st.session_state.sort_newest
)


st.session_state.page_count = max(1, (len(filtered) // PAGE_SIZE) + 1)


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
# LIST VIEW
# =========================
def render_list_view(data):
    start = (st.session_state.page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE

    page_data = data.iloc[start:end]

    st.write(f"Showing {len(page_data)} of {len(data)}")

    for _, row in page_data.iterrows():
        with st.container(border=True):
            st.markdown(f"### {row['title']}")

            if row.get("series"):
                st.markdown(f"**Series:** {row['series']}")

            if row.get("speaker"):
                st.markdown(f"**Speaker:** {row['speaker']}")

            if row.get("description"):
                st.write(row["description"])

            col1, col2 = st.columns(2)

            with col1:
                if row.get("audio_url"):
                    st.link_button("▶ Listen", row["audio_url"])

            with col2:
                if row.get("title_url"):
                    st.link_button("Details ↗", row["title_url"])

    # pagination
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button("Prev") and st.session_state.page > 1:
            st.session_state.page -= 1

    with col3:
        if st.button("Next") and st.session_state.page < st.session_state.page_count:
            st.session_state.page += 1

    with col2:
        st.write(f"Page {st.session_state.page} of {st.session_state.page_count}")


# =========================
# SERIES VIEW
# =========================
def render_series_view(data):
    grouped = data.groupby("series")

    for series_name, group in grouped:
        if not series_name:
            continue

        with st.expander(f"{series_name} ({len(group)})"):

            st.markdown("### Sermons")

            for _, row in group.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row['title']}**")

                    if row.get("series"):
                        st.markdown(f"**Series:** {row['series']}")

                    if row.get("speaker"):
                        st.caption(row["speaker"])

                    if row.get("description"):
                        st.write(row["description"])

                    if row.get("audio_url"):
                        st.link_button("▶ Listen", row["audio_url"])


# =========================
# RENDER
# =========================
st.session_state.page = max(1, min(st.session_state.page, st.session_state.page_count))

if st.session_state.view == "list":
    render_list_view(filtered)
else:
    render_series_view(filtered)