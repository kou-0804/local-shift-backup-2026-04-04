import os


class Settings:
    # P1: masters are the on-disk CSVs (SQLite master store is P3).
    data_dir: str = os.environ.get("SHIFT_DATA_DIR", "shift_scheduler/data")


settings = Settings()
