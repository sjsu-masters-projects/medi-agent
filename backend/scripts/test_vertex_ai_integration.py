#!/usr/bin/env python3
"""Test Vertex AI MedGemma integration.

This script verifies that the Vertex AI endpoint is properly configured
and can generate responses.

Usage:
    python backend/scripts/test_vertex_ai_integration.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

from app.clients.medgemma import MedGemmaClient
from app.config import settings


async def test_vertex_ai():
    """Test Vertex AI MedGemma integration."""
    print("=" * 80)
    print("Vertex AI MedGemma Integration Test")
    print("=" * 80)
    print()

    # Check configuration
    print("Configuration Check:")
    print(f"  GOOGLE_PROJECT_ID: {settings.google_project_id or '❌ NOT SET'}")
    print(f"  VERTEX_AI_LOCATION: {settings.vertex_ai_location}")
    print(f"  VERTEX_AI_MEDGEMMA_ENDPOINT: {settings.vertex_ai_medgemma_endpoint or '❌ NOT SET'}")
    print()

    if not settings.vertex_ai_medgemma_endpoint:
        print("❌ ERROR: VERTEX_AI_MEDGEMMA_ENDPOINT not set in .env")
        print()
        print("Please follow these steps:")
        print("1. Deploy MedGemma via Vertex AI Model Garden")
        print("2. Get the endpoint ID from the console")
        print("3. Add to .env:")
        print("   VERTEX_AI_MEDGEMMA_ENDPOINT=projects/PROJECT_NUMBER/locations/LOCATION/endpoints/ENDPOINT_ID")
        print()
        print("See: backend/docs/MEDGEMMA_VERTEX_AI_QUICK_SETUP.md")
        return False

    if not settings.google_project_id:
        print("❌ ERROR: GOOGLE_PROJECT_ID not set in .env")
        print()
        print("Please add your GCP project ID to .env:")
        print("   GOOGLE_PROJECT_ID=your-project-id")
        return False

    # Initialize client
    print("Initializing MedGemma client...")
    try:
        client = MedGemmaClient(model="google/medgemma-4b-it")
        print("✅ Client initialized")
        print()
    except Exception as e:
        print(f"❌ Failed to initialize client: {e}")
        return False

    # Test simple generation
    print("Test 1: Simple Medical Question")
    print("-" * 80)
    prompt = "What are the common symptoms of diabetes?"
    print(f"Prompt: {prompt}")
    print()

    try:
        print("Generating response...")
        response = await client.generate(
            prompt=prompt,
            system_instruction="You are a medical expert. Provide a brief, clear answer.",
            temperature=0.7,
            max_tokens=256,
        )
        print("✅ Response received:")
        print()
        print(response)
        print()
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        return False

    # Test medical explanation
    print("=" * 80)
    print("Test 2: Lab Result Explanation")
    print("-" * 80)
    prompt = """Explain this lab result to a patient in simple terms:

White Blood Cell Count: 12.5 K/uL (normal: 4.5-11.0)

Patient: 65yo, diabetes, hypertension"""
    print(f"Prompt: {prompt[:100]}...")
    print()

    try:
        print("Generating response...")
        response = await client.generate(
            prompt=prompt,
            system_instruction="You are a medical expert. Use simple language.",
            temperature=0.7,
            max_tokens=512,
        )
        print("✅ Response received:")
        print()
        print(response)
        print()
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        return False

    print("=" * 80)
    print("✅ All tests passed!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Run comprehensive benchmarks:")
    print("   python backend/scripts/run_comprehensive_benchmarks.py")
    print()
    print("2. Review comparison reports in backend/reports/")
    print()
    print("3. IMPORTANT: Stop the Vertex AI endpoint after benchmarking!")
    print("   - Go to: https://console.cloud.google.com/vertex-ai/endpoints")
    print("   - Undeploy and delete the endpoint to avoid charges")
    print()

    return True


if __name__ == "__main__":
    success = asyncio.run(test_vertex_ai())
    sys.exit(0 if success else 1)
