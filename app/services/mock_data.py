import datetime
import hashlib
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import Ticket, TicketTimeline
from app.schemas import TicketCreate
from app.classifier import HeuristicClassifier
from app.config import logger

MOCK_EMAILS = [
    # security_emergency
    {"email_id": "sharma.88@gmail.com", "title": "Locker room door is completely open!", "body": "I am at the society locker room and the main entrance security door is left wide open, unattended. Anyone can walk in! Please address this emergency immediately."},
    {"email_id": "kabir.mehta@yahoo.com", "title": "Water dripping from ceiling in locker room", "body": "There is a water leak in the ceiling of the safe locker area directly above cabinet B. This is a flood hazard for our lockers. Please send maintenance right away."},
    {"email_id": "ananya.s@outlook.com", "title": "Suspicious activity near locker kiosk", "body": "I noticed two strangers lingering around the locker kiosk inputting random screen keys and taking photos of the terminal. We need to check security footage."},
    {"email_id": "rajesh.patel@hotmail.com", "title": "Locker door left open by previous user", "body": "Box number 210 has been left open and unlocked. The door is slightly ajar. I don't see the owner nearby. Please lock it remotely or alert security."},
    {"email_id": "vikram.singh@gmail.com", "title": "Fire alarm ringing in locker basement", "body": "The fire alarm is sounding in the locker room basement. I smell a slight burning odor near the electrical board. Please send emergency response immediately."},
    {"email_id": "neha.gupta@gmail.com", "title": "Kiosk display screen smashed", "body": "The screen of the locker room interaction terminal is shattered and broken, looking like vandalism. It is completely unusable. Please investigate CCTV and replace it."},
    {"email_id": "r_verma@yahoo.com", "title": "My safe box has been tampered with!", "body": "I opened my locker box 104 today and noticed scratches around the door alignment. I am worried someone tried to break in. Please check access logs for this box."},
    {"email_id": "sneha.k@outlook.com", "title": "Locker lock assembly loose", "body": "The electronic lock on locker box 401 is loose and wobbling when touched. It seems highly unsafe. Please send a technician to repair it before my valuables get compromised."},
    
    # access_issue
    {"email_id": "amit.kumar@gmail.com", "title": "Fingerprint scanner not reading my thumbprint", "body": "I am trying to retrieve my document, but the biometric scanner is repeatedly saying 'Invalid Scan'. I have wiped my finger and the sensor but it still declines access."},
    {"email_id": "priya_m@gmail.com", "title": "Kiosk screen frozen on loading screen", "body": "I am standing in the society locker room, and the interactive touch display is stuck on a blue loading logo. Touching the screen does nothing. Please reset the system."},
    {"email_id": "rahul.nair@yahoo.com", "title": "RFID card not recognized", "body": "I tapped my society access card on the locker panel reader, but it is not blinking or registering. The card works on my society main gate. Can you verify my card ID?"},
    {"email_id": "dev_shah@gmail.com", "title": "Locker door 305 did not pop open", "body": "The system screen said 'Locker 305 unlocked', but the door remained shut. I heard the lock click but the box door did not bounce open. Can you trigger it again?"},
    {"email_id": "pooja.jain@outlook.com", "title": "Forgot my locker room PIN code", "body": "I need to pick up my jewelry for a wedding tonight, but I cannot remember my 6-digit access PIN. Please reset my PIN or send a temporary password code to my app."},
    {"email_id": "manish.g@gmail.com", "title": "Kiosk showing offline error status", "body": "The locker terminal displays a red error box reading 'System Offline - Cannot connect to server'. No one in the building can access their vaults. Please fix this network issue."},
    {"email_id": "rohan.roy@yahoo.com", "title": "Face ID authentication failed repeatedly", "body": "My phone app facial scan verification keeps failing when I try to authorize locker room entry. I haven't changed my look. Please reset my biometric profile."},
    {"email_id": "harsh_v@gmail.com", "title": "Locker door jammed after inserting box", "body": "I pushed my safety tray back inside box 115, but the door is stuck halfway and refuses to close or lock shut. The system is sounding a beep alarm. Urgent help needed."},
    {"email_id": "nisha.m@outlook.com", "title": "RFID scanner is blank, no lights", "body": "The card tapping scanner has no green/red light blinking at all. It seems completely dead. I cannot enter the locker room without it scanning. Please check power supply."},
    {"email_id": "siddharth.s@gmail.com", "title": "Bluetooth unlock not working on my app", "body": "My mobile app keeps showing 'Locker Not Found in Range' when I stand near the door. My bluetooth is turned on. Please check why app is not connecting to the door lock."},
    
    # onboarding_kyc
    {"email_id": "pallavi.g@gmail.com", "title": "KYC document keeps getting rejected", "body": "I have uploaded my Aadhaar card thrice, but the app keeps rejecting it saying 'Image blurry'. I took high-resolution photos. Can you verify it manually?"},
    {"email_id": "karan.malhotra@yahoo.com", "title": "Identity verification pending for 3 days", "body": "I submitted my PAN card and selfie for registration three days ago, but the application status still shows 'Pending Review'. I need to store documents urgently."},
    {"email_id": "tanya.b@outlook.com", "title": "Aadhaar OTP not received during registration", "body": "I am trying to register my profile. The app attempts to send an OTP via Aadhaar verification, but I am not receiving any SMS. Can I upload another identity proof?"},
    {"email_id": "vijay.k@gmail.com", "title": "Facial scan setup failed in app onboarding", "body": "During my profile registration, the app tells me to scan my face. However, it crashes every time the camera opens. I am using an iPhone 13. Please assist."},
    {"email_id": "isha.sharma@gmail.com", "title": "Incorrect name on my registration profile", "body": "My name is misspelled on my profile as 'Isha Sarma' instead of 'Isha Sharma', which is causing my PAN card KYC upload to fail. Please correct my profile name."},
    {"email_id": "arjun.rao@yahoo.com", "title": "KYC upload fails with network timeout error", "body": "Every time I upload my address utility bill, the app displays a spinner for 2 minutes and then fails with a timeout error. Is there an alternate portal or email to submit?"},
    {"email_id": "divya_p@gmail.com", "title": "How to register my spouse as secondary user?", "body": "I want to add my husband as an authorized user to my locker box so he can access it. What documents or KYC verification does he need to complete?"},
    {"email_id": "sandeep.t@outlook.com", "title": "KYC status shows 'Document Invalid' error", "body": "I uploaded my driver's license for address validation, but it says invalid. It is a valid government document. Can you manually override and verify my account?"},
    
    # billing_payment
    {"email_id": "gaurav.d@gmail.com", "title": "Double charged for this month's subscription", "body": "My bank statement shows two deductions of Rs 1,500 on August 1st for my society safe deposit box. Please refund the duplicate transaction."},
    {"email_id": "meera_nair@gmail.com", "title": "Autopay failed and locker lock warning received", "body": "My registered credit card expired, and my automatic subscription renewal payment failed. I received a warning about access suspension. I have updated my card, please verify payment."},
    {"email_id": "akash.v@yahoo.com", "title": "Requesting invoice receipt for July payment", "body": "I need the official tax invoice receipt for my safe locker subscription paid in July for my corporate reimbursement. Please email it to my registered id."},
    {"email_id": "shruti.g@outlook.com", "title": "Refund not received for canceled locker", "body": "I canceled my locker plan on July 15th and was promised a pro-rata refund of Rs 2,500 within 5 days. I still haven't received the money. Please check the transaction."},
    {"email_id": "rohit_s@gmail.com", "title": "Card declined error during renewal payment", "body": "The app keeps saying 'Transaction Declined' when I try to pay the locker renewal bill. I checked with my bank, and there are no issues with my card. Please check your payment gateway."},
    {"email_id": "kiran.k@gmail.com", "title": "Wrong subscription tier fee charged", "body": "I subscribed to the Small Locker box (Rs 1,000/month), but my bill shows charges for the Medium box (Rs 1,500/month). Please rectify this billing discrepancy."},
    {"email_id": "neeraj.r@yahoo.com", "title": "Payment invoice does not show society GSTIN", "body": "The invoice received doesn't reflect my society's GST number. I need it corrected to claim input tax credits. Can you issue a revised GST invoice?"},
    {"email_id": "aditi.s@outlook.com", "title": "Auto-renewal charge occurred after cancelation", "body": "I submitted a locker cancellation request on June 20th, but I was still charged Rs 1,500 for July auto-renewal. Please reverse this transaction and close my account."},
    
    # locker_management
    {"email_id": "kartik.s@gmail.com", "title": "Want to upgrade to a larger locker box size", "body": "I currently rent a medium size box, but I need to store some additional property papers and jewelry. I would like to upgrade to a Large locker size. Are there boxes available?"},
    {"email_id": "sheetal.m@gmail.com", "title": "Locker relocation request to a different society", "body": "I am relocating from 'Orchid Heights' to 'Godrej Woods' society next week. I want to transfer my locker subscription and contents to the Godrej Woods cabinet. How can I schedule this?"},
    {"email_id": "pranav.p@yahoo.com", "title": "Termination of locker subscription", "body": "I want to close my safe box and cancel my contract by the end of this month. What is the procedure to clear out my locker and hand over the keys?"},
    {"email_id": "reema.d@outlook.com", "title": "Locker door alignment is slightly crooked", "body": "My locker box 204 door seems misaligned and rubs against the adjacent locker when opening. It opens but requires force. Please adjust the hinges."},
    {"email_id": "vivek_g@gmail.com", "title": "Change locker box number inside society cabinet", "body": "My allocated locker is at the very bottom row, and it is difficult for my elderly parents to bend down to access it. Can we transfer to a middle-row box?"},
    {"email_id": "swati.t@gmail.com", "title": "Terminate my subscription and release deposit", "body": "I have emptied my locker box 302 and want to cancel my locker service immediately. Please refund my security deposit of Rs 5,000 to my account."},
    {"email_id": "deepak.c@yahoo.com", "title": "Requesting helper tray replacement", "body": "The plastic helper organization tray inside my safe box 108 is cracked. Can I get a replacement tray delivered to my society locker locker terminal?"},
    {"email_id": "alok_k@outlook.com", "title": "Transfer locker ownership to family member", "body": "I am relocating abroad permanently. I want to transfer the locker ownership contract to my father. What is the process and authorization documents required?"},
    
    # general_support
    {"email_id": "narendra_s@gmail.com", "title": "What are the safe locker room timings?", "body": "Could you please inform me of the operational hours for the locker room in our society? Is it accessible 24/7 or are there restricted night timings?"},
    {"email_id": "maya.r@gmail.com", "title": "Requesting a PDF user manual guide", "body": "I am a new user and want to understand how to operate the locker room keypad and biometric verification. Can you send me the user manual PDF?"},
    {"email_id": "jay_mehta@yahoo.com", "title": "Is the locker room under CCTV surveillance?", "body": "I want to ensure security before storing gold. Are there cameras active inside the locker room, and is there a security guard outside?"},
    {"email_id": "preeti.s@outlook.com", "title": "Locker box storage capacity specifications", "body": "Can you share the exact dimensions and weight limits for the medium size locker box? I need to verify if my safe box will fit inside it."},
    {"email_id": "ramesh_b@gmail.com", "title": "Are locker contents insured?", "body": "I am planning to store valuable documents. Does Aurm provide insurance coverage against theft or damage for the items inside our lockers?"},
    {"email_id": "snehal.d@gmail.com", "title": "Locker room feedback suggestion", "body": "The locker room lighting is currently very dim. It would be helpful if you could install brighter ceiling LED lights for better visibility at night. Thank you."},
    {"email_id": "varun_t@yahoo.com", "title": "How does the mobile app emergency lock feature work?", "body": "I saw an 'Emergency Lock' option in my mobile app. Can you explain what happens if I click it? Does it block access to my physical locker box?"},
    {"email_id": "tushar.p@outlook.com", "title": "Locker cabinet location in the society", "body": "I just registered my locker but do not know where the cabinet room is located inside 'Prestige Lakeside' society. Can you give me the block number?"}
]


def seed_mock_data(db: Session) -> None:
    """
    Checks if the ticket table is empty. If empty, seeds 50 realistic support 
    tickets classified locally using Heuristics, setting up queue names, SLA, 
    and timeline trails.
    """
    ticket_count = db.query(func.count(Ticket.id)).scalar() or 0
    if ticket_count > 0:
        logger.info(f"Database contains {ticket_count} records. Skipping mock seeding.")
        return

    logger.info("Database is empty. Seeding 50 realistic mock tickets...")
    classifier = HeuristicClassifier()
    
    # Track time back incrementally to create realistic timestamps
    base_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)
    
    seeded_count = 0
    for i, mock_email in enumerate(MOCK_EMAILS):
        try:
            # Classify using deterministic local engine
            classification = classifier.classify(mock_email["title"], mock_email["body"])
            
            # Spread timestamps over the last 5 days
            created_at = base_time + datetime.timedelta(hours=i * 2.4)
            
            # Compute duplicate hash
            data_str = f"{mock_email['email_id'].strip().lower()}|{mock_email['title'].strip().lower()}|{mock_email['body'].strip().lower()}"
            dup_hash = hashlib.sha256(data_str.encode("utf-8")).hexdigest()
            
            # Compute human ticket code
            date_str = created_at.strftime("%Y%m%d")
            ticket_code = f"TKT-{date_str}-{seeded_count+1:05d}"
            
            # Compute SLA Deadline
            sla_windows = {"P0": 0.25, "P1": 2.0, "P2": 24.0, "P3": 48.0}
            hours = sla_windows.get(classification.priority, 48.0)
            sla_deadline = created_at + datetime.timedelta(hours=hours)
            
            # Assign Queue
            category = classification.category
            priority = classification.priority
            if category == "security_emergency" or priority == "P0":
                queue_name = "Emergency"
            elif category in ["access_issue", "locker_management"]:
                queue_name = "Operations"
            elif category == "billing_payment":
                queue_name = "Billing"
            else:
                queue_name = "General Support"
                
            needs_review = classification.confidence < 0.60
            
            db_ticket = Ticket(
                ticket_code=ticket_code,
                duplicate_hash=dup_hash,
                email_id=mock_email["email_id"],
                title=mock_email["title"],
                body=mock_email["body"],
                category=classification.category,
                priority=classification.priority,
                confidence=classification.confidence,
                reasoning=classification.reasoning,
                summary=classification.summary,
                suggested_action=classification.suggested_action,
                draft_reply=classification.draft_reply,
                classification_source="heuristic",
                needs_manual_review=needs_review,
                queue_name=queue_name,
                sla_deadline=sla_deadline,
                explainable_ai=classification.explainable_ai,
                status="resolved" if i % 7 == 0 else ("investigating" if i % 4 == 0 else "open"),
                created_at=created_at,
                updated_at=created_at,
                assigned_to="agent_ops" if i % 3 == 0 else None
            )
            db.add(db_ticket)
            db.flush() # Yields primary key id without commit
            
            # Seed timeline history
            event_created = TicketTimeline(
                ticket_id=db_ticket.id,
                event_type="created",
                description="Ticket ingested from resident email.",
                created_at=created_at
            )
            event_classified = TicketTimeline(
                ticket_id=db_ticket.id,
                event_type="classified",
                description=f"Classification engine resolved category as '{classification.category}' and priority as '{classification.priority}' with {int(classification.confidence * 100)}% confidence (heuristic engine).",
                created_at=created_at
            )
            db.add(event_created)
            db.add(event_classified)
            
            if db_ticket.assigned_to:
                event_assigned = TicketTimeline(
                    ticket_id=db_ticket.id,
                    event_type="assigned",
                    description=f"Assigned to agent '{db_ticket.assigned_to}'.",
                    created_at=created_at
                )
                db.add(event_assigned)
                
            if db_ticket.status != "open":
                event_status = TicketTimeline(
                    ticket_id=db_ticket.id,
                    event_type="status_changed",
                    description=f"Status changed to '{db_ticket.status}'.",
                    created_at=created_at
                )
                db.add(event_status)
                
            seeded_count += 1
        except Exception as e:
            logger.error(f"Failed to seed mock ticket {mock_email['title']}: {e}")

    try:
        db.commit()
        logger.info(f"Successfully seeded {seeded_count} mock tickets with full schemas and timelines.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to commit seeded mock tickets: {e}")
