import os
from fastapi import APIRouter, Request, HTTPException, Depends
from svix.webhooks import Webhook, WebhookVerificationError
from sqlalchemy.orm import Session
from .database import get_db, User

router = APIRouter()

@router.post("/api/webhooks/clerk")
async def clerk_webhook(request: Request, db: Session = Depends(get_db)):
    webhook_secret = os.getenv("CLERK_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    # Get the headers
    headers = request.headers
    svix_id = headers.get("svix-id")
    svix_timestamp = headers.get("svix-timestamp")
    svix_signature = headers.get("svix-signature")

    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(status_code=400, detail="Missing Svix headers")

    # Get the raw body
    payload = await request.body()

    # Verify the webhook signature
    try:
        wh = Webhook(webhook_secret)
        evt = wh.verify(payload, headers)
    except WebhookVerificationError as e:
        print(f"Webhook verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    event_type = evt.get("type")
    data = evt.get("data", {})

    if event_type == "user.created":
        user_id = data.get("id")

        # Safely extract email
        email = None
        email_addresses = data.get("email_addresses", [])
        if email_addresses:
            email = email_addresses[0].get("email_address")

        if user_id:
            try:
                # Check if user already exists (idempotency)
                existing_user = db.query(User).filter(User.id == user_id).first()
                if not existing_user:
                    new_user = User(id=user_id, email=email)
                    db.add(new_user)
                    db.commit()
            except Exception as e:
                db.rollback()
                print(f"Failed to insert user: {e}")

    return {"status": "ok"}
