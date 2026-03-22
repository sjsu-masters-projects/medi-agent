#!/usr/bin/env python3
"""Quick test to verify Gemini API is working.

Usage:
    python backend/scripts/test_gemini_api.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

from app.clients.gemini import GeminiClient
from app.config import settings


async def test_gemini():
    """Test Gemini API."""
    print("=" * 80)
    print("Gemini API Test")
    print("=" * 80)
    print()

    # Check API key
    if not settings.google_api_key:
        print("❌ ERROR: GOOGLE_API_KEY not set in .env")
        return False

    print(f"✅ API Key configured: {settings.google_api_key[:20]}...")
    print()

    # Test Gemini Flash
    print("Testing Gemini 2.5 Flash...")
    print("-" * 80)
    try:
        client = GeminiClient(model="gemini-2.5-flash")
        response = await client.generate(
            prompt="What are the common symptoms of diabetes? (Brief answer)",
            system_instruction="You are a medical expert. Be concise.",
            temperature=0.7,
            max_tokens=256,
        )
        print("✅ Gemini Flash working!")
        print()
        print("Response:")
        print(response)
        print()
    except Exception as e:
        print(f"❌ Gemini Flash failed: {e}")
        return False

    # Test Gemini Pro
    print("=" * 80)
    print("Testing Gemini 2.5 Pro...")
    print("-" * 80)
    try:
        client = GeminiClient(model="gemini-2.5-pro")
        response = await client.generate(
            prompt="Explain the mechanism of action of ACE inhibitors. (Brief answer)",
            system_instruction="You are a clinical pharmacist. Be concise.",
            temperature=0.7,
            max_tokens=256,
        )
        print("✅ Gemini Pro working!")
        print()
        print("Response:")
        print(response)
        print()
    except Exception as e:
        print(f"❌ Gemini Pro failed: {e}")
        return False

    print("=" * 80)
    print("✅ All Gemini models working!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Deploy MedGemma to Vertex AI (see: backend/docs/READY_TO_BENCHMARK.md)")
    print("2. Run comprehensive benchmarks")
    print()

    return True


if __name__ == "__main__":
    success = asyncio.run(test_gemini())
    sys.exit(0 if success else 1)
