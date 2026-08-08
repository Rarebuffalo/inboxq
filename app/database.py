import datetime
from typing import Generator, List
from sqlalchemy import create_engine, String, Float, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, relationship
from app.config import settings, logger

# Configure connection pool for SQLite. 
# check_same_thread=False is required for SQLite to support concurrent web requests.
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

# Central session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    SQLAlchemy 2.0 Declarative Base class mapping models to typed fields.
    """
    pass


class Ticket(Base):
    """
    Ticket model representing classified customer support emails.
    """
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    ticket_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    duplicate_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    email_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Classification Metadata
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Operational Responses
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    draft_reply: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Ticket State & Operations
    status: Mapped[str] = mapped_column(String(50), default="open", index=True, nullable=False)
    classification_source: Mapped[str] = mapped_column(String(50), default="heuristic", nullable=False)
    needs_manual_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    queue_name: Mapped[str] = mapped_column(String(50), default="General Support", index=True, nullable=False)
    sla_deadline: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    explainable_ai: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False
    )
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Relational link to ticket audit log events
    timeline: Mapped[List["TicketTimeline"]] = relationship(
        "TicketTimeline", 
        back_populates="ticket", 
        cascade="all, delete-orphan",
        order_by="TicketTimeline.created_at.asc()"
    )


class TicketTimeline(Base):
    """
    Timeline audit trail capturing operational lifecycle triggers and state transitions.
    """
    __tablename__ = "ticket_timeline"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False
    )

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="timeline")


def init_db() -> None:
    """
    Initialize SQLite database tables.
    Invoked during application startup.
    """
    logger.info("Initializing database schema...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        raise e


def get_db() -> Generator[sessionmaker, None, None]:
    """
    Dependency Injection provider yielding a scoped database session.
    Automatically closes session on request lifecycle tear down.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
