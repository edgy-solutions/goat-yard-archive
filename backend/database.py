from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import datetime

# Use DATABASE_URL from env or default to local docker postgres
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/vectors")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    # Clerk User ID (e.g., "user_2qX...")
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    print("Initialize Database Tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created.")
    except Exception as e:
        print(f"❌ Database init failed: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
