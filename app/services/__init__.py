import datetime
import hashlib
from typing import List, Optional, Dict
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from app.database import Ticket, TicketTimeline
from app.schemas import TicketCreate, TicketUpdate, TicketClassification, TicketAnalytics


class TicketService:
    """
    Service layer coordinating core business logic, database transactions, 
    classification executions, SLAs, queues, and timeline history.
    """

    def _generate_duplicate_hash(self, email_id: str, title: str, body: str) -> str:
        """
        Generates a deterministic SHA-256 hash of email credentials and content to prevent duplication.
        """
        data_str = f"{email_id.strip().lower()}|{title.strip().lower()}|{body.strip().lower()}"
        return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

    def _generate_ticket_code(self, db: Session) -> str:
        """
        Generates a human-friendly ticket code in the format: TKT-YYYYMMDD-00001
        """
        today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        prefix = f"TKT-{today_str}-"
        
        # Query total count of codes matching today's prefix to calculate serial
        statement = select(func.count(Ticket.id)).where(Ticket.ticket_code.like(f"{prefix}%"))
        count = db.execute(statement).scalar() or 0
        serial = count + 1
        return f"{prefix}{serial:05d}"

    def _calculate_sla(self, created_at: datetime.datetime, priority: str) -> datetime.datetime:
        """
        Calculates SLA deadline based on priority levels:
        - P0: 15 minutes (0.25 hours)
        - P1: 2 hours
        - P2: 24 hours
        - P3: 48 hours
        """
        sla_windows = {
            "P0": 0.25,
            "P1": 2.0,
            "P2": 24.0,
            "P3": 48.0
        }
        hours = sla_windows.get(priority, 48.0)
        return created_at + datetime.timedelta(hours=hours)

    def _assign_queue(self, category: str, priority: str) -> str:
        """
        Routes ticket to logical queue partitions based on priority and category:
        - Emergency: category is security_emergency or priority is P0
        - Operations: category is access_issue or locker_management
        - Billing: category is billing_payment
        - General Support: default
        """
        if category == "security_emergency" or priority == "P0":
            return "Emergency"
        elif category in ["access_issue", "locker_management"]:
            return "Operations"
        elif category == "billing_payment":
            return "Billing"
        else:
            return "General Support"

    def create_ticket(
        self, 
        db: Session, 
        ticket_in: TicketCreate, 
        classification: TicketClassification,
        source: str
    ) -> Ticket:
        """
        Persist a classified support ticket, preventing duplicate insertions via SHA-256 hash checks,
        generating human-friendly codes, allocating queues, setting SLAs, and logging timeline entries.
        """
        from app.config import logger
        
        dup_hash = this_hash = self._generate_duplicate_hash(ticket_in.email_id, ticket_in.title, ticket_in.body)
        
        # Check for duplication
        dup_statement = select(Ticket).where(Ticket.duplicate_hash == dup_hash)
        existing_ticket = db.execute(dup_statement).scalars().first()
        if existing_ticket:
            logger.warning(f"Duplicate ticket detected for hash: {dup_hash}. Returning existing ticket code: {existing_ticket.ticket_code}")
            return existing_ticket

        # Calculate metadata
        created_at = datetime.datetime.now(datetime.timezone.utc)
        ticket_code = self._generate_ticket_code(db)
        sla_deadline = self._calculate_sla(created_at, classification.priority)
        queue_name = self._assign_queue(classification.category, classification.priority)
        needs_review = classification.confidence < 0.60

        db_ticket = Ticket(
            ticket_code=ticket_code,
            duplicate_hash=dup_hash,
            email_id=ticket_in.email_id,
            title=ticket_in.title,
            body=ticket_in.body,
            category=classification.category,
            priority=classification.priority,
            confidence=classification.confidence,
            reasoning=classification.reasoning,
            summary=classification.summary,
            suggested_action=classification.suggested_action,
            draft_reply=classification.draft_reply,
            classification_source=source,
            needs_manual_review=needs_review,
            queue_name=queue_name,
            sla_deadline=sla_deadline,
            explainable_ai=classification.explainable_ai,
            status="open",
            created_at=created_at,
            updated_at=created_at
        )
        db.add(db_ticket)
        db.commit()
        db.refresh(db_ticket)
        
        # Seed timeline history
        self._add_timeline_event(db, db_ticket.id, "created", "Ticket ingested from resident email.")
        self._add_timeline_event(
            db, 
            db_ticket.id, 
            "classified", 
            f"Classification engine resolved category as '{classification.category}' and priority as '{classification.priority}' with {int(classification.confidence * 100)}% confidence ({source} engine)."
        )
        
        return db_ticket

    def _add_timeline_event(self, db: Session, ticket_id: int, event_type: str, description: str) -> None:
        """
        Creates and logs a lifecycle event in the TicketTimeline database.
        """
        event = TicketTimeline(
            ticket_id=ticket_id,
            event_type=event_type,
            description=description,
            created_at=datetime.datetime.now(datetime.timezone.utc)
        )
        db.add(event)
        db.commit()

    def get_ticket_by_id(self, db: Session, ticket_id: int) -> Optional[Ticket]:
        """
        Retrieve a ticket record by its primary key identifier.
        """
        statement = select(Ticket).where(Ticket.id == ticket_id)
        result = db.execute(statement)
        return result.scalar_one_or_none()

    def list_tickets(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> List[Ticket]:
        """
        Retrieve a list of tickets with paginated offsets, sorting, and complex filtering options.
        """
        statement = select(Ticket)
        
        # Apply optional filters
        if category:
            statement = statement.where(Ticket.category == category)
        if priority:
            statement = statement.where(Ticket.priority == priority)
        if status:
            statement = statement.where(Ticket.status == status)
        if search:
            search_clause = or_(
                Ticket.title.ilike(f"%{search}%"),
                Ticket.body.ilike(f"%{search}%"),
                Ticket.email_id.ilike(f"%{search}%"),
                Ticket.ticket_code.ilike(f"%{search}%")
            )
            statement = statement.where(search_clause)
            
        # Determine sorting column
        sort_column = Ticket.created_at
        if sort_by == "priority":
            sort_column = Ticket.priority
        elif sort_by == "category":
            sort_column = Ticket.category
        elif sort_by == "status":
            sort_column = Ticket.status
        elif sort_by == "confidence":
            sort_column = Ticket.confidence
            
        if sort_order == "asc":
            statement = statement.order_by(sort_column.asc())
        else:
            statement = statement.order_by(sort_column.desc())
            
        statement = statement.offset(skip).limit(limit)
        result = db.execute(statement)
        return list(result.scalars().all())

    def update_ticket(
        self, 
        db: Session, 
        ticket_id: int, 
        update_in: TicketUpdate
    ) -> Optional[Ticket]:
        """
        Apply manual updates or overrides (including category, priority, status, 
        assigned agent, and manual draft reply overrides). Logs updates to timeline.
        """
        db_ticket = self.get_ticket_by_id(db, ticket_id)
        if not db_ticket:
            return None
            
        update_data = update_in.model_dump(exclude_unset=True)
        
        # Log overrides to timeline audit logs
        for key, value in update_data.items():
            old_value = getattr(db_ticket, key)
            if old_value != value:
                if key == "status":
                    self._add_timeline_event(db, ticket_id, "status_changed", f"Status changed from '{old_value}' to '{value}'.")
                elif key == "priority":
                    self._add_timeline_event(db, ticket_id, "override_priority", f"Priority overridden from '{old_value}' to '{value}'.")
                    # Recalculate SLA on priority change
                    db_ticket.sla_deadline = self._calculate_sla(db_ticket.created_at, value)
                    # Recalculate queue name
                    db_ticket.queue_name = self._assign_queue(db_ticket.category, value)
                elif key == "category":
                    self._add_timeline_event(db, ticket_id, "override_category", f"Category overridden from '{old_value}' to '{value}'.")
                    db_ticket.queue_name = self._assign_queue(value, db_ticket.priority)
                elif key == "assigned_to":
                    self._add_timeline_event(db, ticket_id, "assigned", f"Assigned to agent '{value}'.")
                elif key == "draft_reply":
                    self._add_timeline_event(db, ticket_id, "draft_reply_edited", "Draft reply edited by support agent.")
                    
                setattr(db_ticket, key, value)
        
        db_ticket.updated_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
        db.refresh(db_ticket)
        return db_ticket

    def get_analytics(self, db: Session) -> TicketAnalytics:
        """
        Perform database aggregations to compute ticket statistics for dashboard rendering.
        """
        total = db.query(func.count(Ticket.id)).scalar() or 0
        
        # Fetch counts by priority
        priority_results = db.query(Ticket.priority, func.count(Ticket.id)).group_by(Ticket.priority).all()
        by_priority = {priority: count for priority, count in priority_results}
        
        for p in ["P0", "P1", "P2", "P3"]:
            by_priority.setdefault(p, 0)
            
        # Fetch counts by category
        category_results = db.query(Ticket.category, func.count(Ticket.id)).group_by(Ticket.category).all()
        by_category = {category: count for category, count in category_results}
        
        for c in ["security_emergency", "access_issue", "onboarding_kyc", "billing_payment", "locker_management", "general_support"]:
            by_category.setdefault(c, 0)
            
        # Fetch counts by status
        status_results = db.query(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status).all()
        by_status = {status: count for status, count in status_results}
        
        for s in ["open", "investigating", "resolved"]:
            by_status.setdefault(s, 0)
            
        # Average confidence calculation
        avg_conf = db.query(func.avg(Ticket.confidence)).scalar() or 0.0
        
        # Calculate starting datetime of today in UTC
        today_start = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        tickets_today = db.query(func.count(Ticket.id)).filter(Ticket.created_at >= today_start).scalar() or 0
        
        return TicketAnalytics(
            total_tickets=total,
            by_priority=by_priority,
            by_category=by_category,
            by_status=by_status,
            average_confidence=round(float(avg_conf), 2),
            tickets_today=tickets_today,
            p0_count=by_priority.get("P0", 0),
            p1_count=by_priority.get("P1", 0)
        )


# Global service instance
ticket_service = TicketService()
