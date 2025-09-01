import os
from typing import Generator, Optional

from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine, Session as SQLModelSession
from sqlalchemy.orm import sessionmaker

# carga .env
load_dotenv()

# ejemplo: "mysql+pymysql://user:pass@localhost:3306/mi_db"
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")

# solo sqlite necesita check_same_thread
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# crear engine (MySQL no necesita connect_args)
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

# IMPORTANT: class_=SQLModelSession para que SessionLocal() devuelva sqlmodel.Session (con .exec)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=SQLModelSession)

def init_db() -> None:
    SQLModel.metadata.create_all(bind=engine)

def get_session() -> Generator[SQLModelSession, None, None]:
    db: Optional[SQLModelSession] = None
    try:
        db = SessionLocal()
        yield db
    finally:
        if db is not None:
            db.close()