from sqlalchemy import create_engine, Column, String, DateTime, Integer, ForeignKey
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

class SearchHistory(Base):
    __tablename__ = "search_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True) # E.g., Clerk ID or Anonymous IP
    query_text = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    print("Initialize Database Tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created.")
    except Exception as e:
        print(f"❌ Database init failed: {e}")
        
    print("Initialize Weaviate Cache Collections...")
    try:
        import weaviate
        import weaviate.classes as wvc
        
        weaviate_url = os.getenv("WEAVIATE_URL", "localhost")
        
        if weaviate_url != "localhost":
            if "://" not in weaviate_url:
                if ":" in weaviate_url:
                    http_host = weaviate_url.split(":")[0]
                    try:
                        http_port = int(weaviate_url.split(":")[-1])
                    except:
                        http_port = int(os.getenv("WEAVIATE_PORT", 80))
                else:
                    http_host = weaviate_url
                    http_port = int(os.getenv("WEAVIATE_PORT", 80))
            else:
                from urllib.parse import urlparse
                parsed = urlparse(weaviate_url)
                http_host = parsed.hostname
                http_port = parsed.port if parsed.port is not None else int(os.getenv("WEAVIATE_PORT", 80))
                
            grpc_host = os.getenv("WEAVIATE_GRPC_HOST", http_host)
            grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
            
            client = weaviate.connect_to_custom(
                http_host=http_host,
                http_port=http_port,
                http_secure=weaviate_url.startswith("https"),
                grpc_host=grpc_host,
                grpc_port=grpc_port,
                grpc_secure=weaviate_url.startswith("https"),
                skip_init_checks=True
            )
        else:
            client = weaviate.connect_to_local()
            
        if not client.collections.exists("GroupSummary"):
            client.collections.create(
                name="GroupSummary",
                description="JIT Summary Cache for Matrix Endpoint",
                vectorizer_config=wvc.config.Configure.Vectorizer.none(),
                properties=[
                    wvc.config.Property(name="group_hash", data_type=wvc.config.DataType.TEXT, tokenization=wvc.config.Tokenization.FIELD),
                    wvc.config.Property(name="summary_text", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="group_name", data_type=wvc.config.DataType.TEXT)
                ]
            )
            print("✅ GroupSummary collection created.")
        client.close()
    except Exception as e:
        print(f"❌ Weaviate init failed: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
