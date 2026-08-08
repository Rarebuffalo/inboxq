import csv
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import TicketCreate, TicketResponse, TicketUpdate, TicketAnalytics
from app.services import ticket_service
from app.classifier import get_classifier
from app.config import logger

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.post(
    "/classify", 
    response_model=TicketResponse, 
    status_code=status.HTTP_201_CREATED,
    summary="Classify and create a ticket from an email"
)
def classify_ticket(ticket_in: TicketCreate, db: Session = Depends(get_db)) -> TicketResponse:
    """
    Ingests an email payload, runs duplicate checking, invokes classification engines, 
    allocates queue routing, sets SLA windows, seeds timeline events, and fires P0/P1 warning signals.
    """
    logger.info(f"Ingestion request for email_id: {ticket_in.email_id}")
    
    classifier = get_classifier()
    try:
        # Run classification engine
        classification = classifier.classify(ticket_in.title, ticket_in.body)
        source = getattr(classifier, "last_source", "heuristic")
    except Exception as e:
        logger.error(f"Classification failure: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Classification process failed: {str(e)}"
        )
        
    db_ticket = ticket_service.create_ticket(db, ticket_in, classification, source)
    
    # Check if duplicate was returned
    # (If duplicate, ID already exists, and we don't dispatch duplicate alerts)
    if getattr(db_ticket, "_is_duplicate", False):
        return db_ticket

    # Part 7: Simulated Automations for P0/P1
    if db_ticket.priority in ["P0", "P1"]:
        logger.warning(
            f"[WEBHOOK SIMULATION] Dispatched high-priority alert webhook for ticket ID {db_ticket.id}. "
            f"Code: {db_ticket.ticket_code}, Priority: {db_ticket.priority}, Queue: {db_ticket.queue_name}."
        )
        
    return db_ticket


@router.get(
    "/export", 
    summary="Export ticket queue to CSV format"
)
def export_tickets(
    category: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
) -> StreamingResponse:
    """
    Exports filtered support queue entries directly in CSV format.
    """
    logger.info("CSV Support queue export request initialized.")
    tickets = ticket_service.list_tickets(
        db=db,
        limit=1000, # Large bound for exports
        category=category,
        priority=priority,
        status=status,
        search=search
    )
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "Ticket Code", "Email ID", "Title", "Category", "Priority", 
        "Confidence", "Status", "Queue Name", "SLA Deadline", "Created At", 
        "Needs Manual Review", "Assigned To"
    ])
    
    # Write rows
    for t in tickets:
        writer.writerow([
            t.ticket_code,
            t.email_id,
            t.title,
            t.category,
            t.priority,
            t.confidence,
            t.status,
            t.queue_name,
            t.sla_deadline.strftime("%Y-%m-%d %H:%M:%S") if t.sla_deadline else "None",
            t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "Yes" if t.needs_manual_review else "No",
            t.assigned_to or "Unassigned"
        ])
        
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tickets_export.csv"}
    )


@router.get(
    "", 
    response_model=List[TicketResponse],
    summary="List support tickets with optional filtering, search, and sorting"
)
def get_tickets(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db)
) -> List[TicketResponse]:
    """
    Returns a paginated list of tickets matching filters. Sorting parameters are supported.
    """
    return ticket_service.list_tickets(
        db=db,
        skip=skip,
        limit=limit,
        category=category,
        priority=priority,
        status=status,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order
    )


@router.get(
    "/analytics", 
    response_model=TicketAnalytics,
    summary="Retrieve real-time ticket stats and totals"
)
def get_analytics(db: Session = Depends(get_db)) -> TicketAnalytics:
    """
    Calculates operational aggregates to feed the Ops Analytics interface.
    """
    return ticket_service.get_analytics(db)


@router.get(
    "/{ticket_id}", 
    response_model=TicketResponse,
    summary="Retrieve detailed ticket information"
)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)) -> TicketResponse:
    """
    Queries and returns a single ticket object by its unique database ID.
    """
    ticket = ticket_service.get_ticket_by_id(db, ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket with ID {ticket_id} not found."
        )
    return ticket


@router.patch(
    "/{ticket_id}", 
    response_model=TicketResponse,
    summary="Update a ticket state or classification"
)
def update_ticket(
    ticket_id: int, 
    update_in: TicketUpdate, 
    db: Session = Depends(get_db)
) -> TicketResponse:
    """
    Applies manual overrides directly on a target ticket, logging transitions in the timeline audit table.
    """
    logger.info(f"Manual override request for ticket ID {ticket_id}: {update_in.model_dump(exclude_unset=True)}")
    
    ticket = ticket_service.update_ticket(db, ticket_id, update_in)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket with ID {ticket_id} not found."
        )
    return ticket
