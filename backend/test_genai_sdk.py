#!/usr/bin/env python3
"""Quick test of Google Gen AI SDK for Gemini 3.1 Pro Preview."""

import asyncio
import sys
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent / "src"
sys.path.insert(0, str(backend_src))

from app.clients.gemini import GeminiClient
from app.config import settings


async def main():
    """Test Gemini 3.1 Pro Preview."""
    print("Testing Gemini 3.1 Pro Preview with Gen AI SDK...")
    print(f"Project: {settings.google_project_id}")
    print()

    client = GeminiClient(model="gemini-3.1-pro-preview", use_vertex_ai=True)

    prompt = """Patient: 62yo started Atorvastatin 80mg 3 weeks ago.
Now reports: muscle pain, weakness, dark urine.

Is this an adverse drug reaction? What should be done?"""

    system_instruction = "You are a clinical pharmacist."

    print("Sending request...")
    print()

    response = await client.generate(
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=0.7,
        max_tokens=1024,
    )

    print(f"Response length: {len(response)} chars")
    print(f"Response word count: {len(response.split())}")
    print()
    print("Response:")
    print("=" * 80)
    print(response)
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
