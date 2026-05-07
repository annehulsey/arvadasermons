from .paths import SERMONS_PATH
from .libsyn_scrape import update_new_sermons

def main():

    SERMONS_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not SERMONS_PATH.exists():
        SERMONS_PATH.touch()

    update_new_sermons(max_pages=10, max_known_streak=3)


if __name__ == "__main__":
    main()