"""
database/db_setup.py
====================
Configures the SQLAlchemy engine, session factory, and declarative base.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    db_filename = "ivc_local.db"
    try:
        # Check if the current directory is writable by touching a temporary file
        test_file = Path("._db_write_test")
        test_file.touch()
        test_file.unlink()
        db_path = Path(db_filename).resolve()
    except (OSError, IOError):
        # Fallback to system temp directory if current directory is read-only
        db_path = Path(tempfile.gettempdir()) / db_filename
    DATABASE_URL = f"sqlite:///{db_path.as_posix()}"

# Configure sqlite specifically for thread safety in multi-threaded/FastAPI runs
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency for obtaining database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
