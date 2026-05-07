import pandas as pd
import json

from .paths import SERMONS_PATH

def load_data(drop_bonus_episodes=True,drop_devotionals=True):
    data = []
    with open(SESRMONS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            data.append(json.loads(line))
    data = pd.DataFrame(data)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    if drop_bonus_episode:
        idx = data['series']=='Bonus Episode'
        data = data[~idx]
    if drop_devotionals:
        data = data[~data['series'].str.contains("devotion", case=False, na=False)]
    return data
