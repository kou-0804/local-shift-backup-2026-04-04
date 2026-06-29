import os


class Settings:
    # P1: masters are the on-disk CSVs (SQLite master store is P3).
    data_dir: str = os.environ.get("SHIFT_DATA_DIR", "shift_scheduler/data")
    # P2a-2: roster persistence DB (frozen rosters, edits, undo/redo).
    db_path: str = os.environ.get("SHIFT_DB_PATH", "webapp_data/shift.db")


settings = Settings()
