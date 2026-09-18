"""What is left of the agent packages.

Only document ingestion still lives here. Triage moved to
`app/adk/agents/care_coordinator/`, symptom capture to `app/followup/`, and SOAP
summarization to `services/soap_note_service.py` — each either framework-free or on the
agent runtime.

There is deliberately no shared base class re-exported any more. The one that lived here
required every agent to hold a state graph, which is precisely the coupling these moves
were for.
"""
