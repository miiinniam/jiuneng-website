"""轻量持久化 —— SQLite（DEVELOPMENT_GOALS.md §2 提到的轻量部署方案）。

目前只有"模板"这一张表需要真正持久化；报价历史/批量结果暂时不落库，
按需求做完就返回给前端，等以后要做历史记录页面时再加。
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.services._paths import resource_dir

DATA_DIR = resource_dir() / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR / 'osrm_plus.db'}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
