from datetime import datetime
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from google_services import (
    get_google_services,
    fetch_unread_emails,
    get_upcoming_calendar_events,
    create_calendar_event,
    create_gmail_draft
)
import config

# Pydantic schema with Calendar & Scheduling parameters
class EmailAnalysis(BaseModel):
    is_important: bool = Field(description="True if email requires a response; False for spam/newsletters.")
    urgency_reasoning: str = Field(description="Reasoning behind classification.")
    is_meeting_request: bool = Field(description="True if email requests or proposes a meeting/call.")
    event_title: str = Field(default="", description="Suggested title for calendar event, if applicable.")
    start_time_iso: str = Field(default="", description="ISO-8601 formatted start time (e.g., YYYY-MM-DDTHH:MM:SSZ) if scheduling.")
    end_time_iso: str = Field(default="", description="ISO-8601 formatted end time if scheduling.")
    draft_response: str = Field(description="Draft response text. Include meeting confirmation details if scheduling.")

def process_inbox():
    gmail_service, calendar_service = get_google_services()
    emails = fetch_unread_emails(gmail_service, max_results=5)

    if not emails:
        print("No unread emails found.")
        return

    # Get current user's schedule to prevent double-booking
    schedule_context = get_upcoming_calendar_events(calendar_service, days_ahead=3)
    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    llm = ChatOpenAI(model=config.MODEL_NAME, temperature=0.2)
    structured_llm = llm.with_structured_output(EmailAnalysis)

    prompt = ChatPromptTemplate.from_template(
        """You are an executive AI assistant managing an inbox and calendar.

        Current Date & Time: {current_time}
        User's Existing Calendar Schedule (Next 3 Days):
        {existing_schedule}

        Analyze the incoming email below:
        1. Determine if it's important and requires a reply.
        2. Check if it involves scheduling a meeting or call.
        3. If it is a meeting request, parse the proposed time (or choose an open slot given the existing schedule).
           Provide ISO 8601 timestamps (UTC format: YYYY-MM-DDTHH:MM:SSZ) for `start_time_iso` and `end_time_iso`.
        4. Write a professional draft response.

        Sender: {sender}
        Subject: {subject}
        Content:
        {body}
        """
    )

    chain = prompt | structured_llm

    for email in emails:
        print(f"\nProcessing Email: '{email['subject']}' from {email['sender']}")
        result = chain.invoke({
            "current_time": current_datetime,
            "existing_schedule": schedule_context,
            "sender": email["sender"],
            "subject": email["subject"],
            "body": email["body"]
        })

        print(f"  - Important: {result.is_important}")
        print(f"  - Meeting Request: {result.is_meeting_request}")
        print(f"  - Reasoning: {result.urgency_reasoning}")

        # Handle Calendar Integration if meeting detected
        calendar_link = None
        if result.is_important and result.is_meeting_request and result.start_time_iso:
            print("  - Action: Scheduling Calendar Event...")
            try:
                calendar_link = create_calendar_event(
                    calendar_service=calendar_service,
                    summary=result.event_title or f"Meeting with {email['sender']}",
                    start_iso=result.start_time_iso,
                    end_iso=result.end_time_iso,
                    attendee_email=email["sender"]
                )
                print(f"  ✅ Calendar Event Created: {calendar_link}")
            except Exception as e:
                print(f"  ⚠️ Could not create calendar event: {e}")

        # Create Draft in Gmail
        if result.is_important:
            final_draft_text = result.draft_response
            if calendar_link:
                final_draft_text += f"\n\n(Note: Calendar invitation sent for {result.start_time_iso})"

            draft = create_gmail_draft(
                gmail_service=gmail_service,
                to_email=email["sender"],
                subject=email["subject"],
                body=final_draft_text,
                thread_id=email["thread_id"]
            )
            print(f"  ✅ Draft Created in Gmail (Draft ID: {draft['id']})")

if __name__ == "__main__":
    process_inbox()
