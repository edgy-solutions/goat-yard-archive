import os
import svix
import json
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from .database import get_db, User

router = APIRouter()

CLERK_WEBHOOK_SECRET = os.getenv("CLERK_WEBHOOK_SECRET")

@router.post("/webhooks/clerk")
async def clerk_webhook(request: Request, db: Session = Depends(get_db)):
    if not CLERK_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook Secret not configured")

    # 1. Get Headers
    headers = request.headers
    svix_id = headers.get("svix-id")
    svix_timestamp = headers.get("svix-timestamp")
    svix_signature = headers.get("svix-signature")

    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(status_code=400, detail="Missing svix headers")

    # 2. Get Body
    payload = await request.body()
    
    # 3. Verify Signature
    wh = svix.Webhook(CLERK_WEBHOOK_SECRET)
    try:
        msg = wh.verify(payload, headers)
    except svix.exceptions.WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 4. Handle Events
    event_type = msg.get("type")
    data = msg.get("data", {})

    if event_type == "user.created":
        user_id = data.get("id")
        email_addresses = data.get("email_addresses", [])
        primary_email = None
        if email_addresses:
            primary_email = email_addresses[0].get("email_address")
        
        if user_id:
            # Upsert
            existing = db.query(User).filter(User.id == user_id).first()
            if not existing:
                new_user = User(id=user_id, email=primary_email)
                db.add(new_user)
                try:
                    db.commit()
                    print(f"✅ Synced Check User: {user_id}")
                except Exception as e:
                    db.rollback()
                    print(f"❌ Failed to insert user: {e}")
            else:
                print(f"User {user_id} already exists.")

    return {"status": "ok"}
