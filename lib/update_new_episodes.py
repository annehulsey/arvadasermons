from .paths import EPISODES_PATH
from .libsyn_scrape import update_new_episodes

def main():

    EPISODES_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not EPISODES_PATH.exists():
        EPISODES_PATH.touch()

    update_new_episodes(max_pages=10, max_known_streak=3)


if __name__ == "__main__":
    main()