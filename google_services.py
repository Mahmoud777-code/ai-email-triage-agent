import base64
import os.path
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import config

def get_google_services():
    """Authenticates the user and returns both Gmail and Calendar service instances."""
    creds = None
    if os.path.exists(config.TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                config.CREDENTIALS_FILE, config.SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        with open(config.TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    gmail_service = build("gmail", "v1", credentials=creds)
    calendar_service = build("calendar", "v3", credentials=creds)
    return gmail_service, calendar_service

def fetch_unread_emails(service, max_results=5):
    """Fetches unread emails from the user's Inbox."""
    results = service.users().messages().list(
        userId="me", q="is:unread label:INBOX", maxResults=max_results
    ).execute()
    
    messages = results.get("messages", [])
    emails = []

    for msg in messages:
        msg_detail = service.users().messages().get(userId="me", id=msg["id"]).execute()
        payload = msg_detail.get("payload", {})
        headers = payload.get("headers", [])

        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
        thread_id = msg_detail.get("threadId")

        body = ""
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                    break
        elif "body" in payload and "data" in payload["body"]:
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

        emails.append({
            "id": msg["id"],
            "thread_id": thread_id,
            "sender": sender,
            "subject": subject,
            "body": body[:2000]
        })

    return emails

def get_upcoming_calendar_events(calendar_service, days_ahead=3):
    """Fetches upcoming calendar events to check availability."""
    now = datetime.now(timezone.utc).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat()

    events_result = calendar_service.events().list(
        calendarId="primary",
        timeMin=now,
        timeMax=future,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = events_result.get("items", [])
    formatted_events = []
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        summary = event.get("summary", "Busy")
        formatted_events.append(f"- {summary}: {start} to {end}")

    return "\n".join(formatted_events) if formatted_events else "No upcoming events scheduled."

def create_calendar_event(calendar_service, summary, start_iso, end_iso, attendee_email=None):
    """Schedules a new event in Google Calendar."""
    event = {
        "summary": summary,
        "start": {"dateTime": start_iso, "timeZone": "UTC"},
        "end": {"dateTime": end_iso, "timeZone": "UTC"},
        "description": "Automatically scheduled via AI Email Agent."
    }

    if attendee_email:
        event["attendees"] = [{"email": attendee_email}]

    created_event = calendar_service.events().insert(
        calendarId="primary", body=event, sendUpdates="all"
    ).execute()

    return created_event.get("htmlLink")

def create_gmail_draft(gmail_service, to_email, subject, body, thread_id):
    """Creates a draft response in Gmail."""
    message = EmailMessage()
    message.set_content(body)
    message["To"] = to_email
    message["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    create_message = {
        "message": {
            "raw": encoded_message,
            "threadId": thread_id
        }
    }

    draft = gmail_service.users().drafts().create(userId="me", body=create_message).execute()
    return draft
