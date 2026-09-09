from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker

Path("data").mkdir(exist_ok=True)
engine = create_engine("sqlite:///data/capacity.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class CapacityPoint(Base):
    __tablename__ = "capacity_points"
    id = Column(Integer, primary_key=True)
    pipeline = Column(String, index=True, nullable=False)
    section = Column(String, index=True, nullable=False)
    gas_day = Column(Date, index=True, nullable=False)
    cycle = Column(String, default="TIMELY")
    point_id = Column(String, index=True)
    point_name = Column(String)
    direction = Column(String)
    operating_capacity = Column(Float)
    scheduled = Column(Float)
    available = Column(Float)
    primary_scheduled = Column(Float)
    secondary_prime = Column(Float)
    secondary_scheduled = Column(Float)
    interruptible_scheduled = Column(Float)
    source_url = Column(Text)
    retrieved_at = Column(DateTime, nullable=False)
    source_status = Column(String, default="live")
    __table_args__ = (UniqueConstraint("pipeline", "section", "gas_day", "cycle", "point_id", "point_name", "direction", name="uq_capacity_snapshot"),)

class RefreshRun(Base):
    __tablename__ = "refresh_runs"
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)
    status = Column(String)
    message = Column(Text)

Base.metadata.create_all(bind=engine)
