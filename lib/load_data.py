import pandas as pd
import json

from .paths import EPISODES_PATH

def load_data(drop_bonus_episodes=True):
    data = []
    with open(EPISODES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            data.append(json.loads(line))
    data = pd.DataFrame(data)
    if drop_bonus_episodes:
        idx = data['series']=='Bonus Episode'
        data = data[~idx]
    return data
