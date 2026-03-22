#!/usr/bin/env python3
"""Quick benchmark with just 2 scenarios to test Gemini 3.1 models."""

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

from app.clients.gemini import GeminiClient
from app.clients.medgemma import MedGemmaClient
from app.config import settings


async def main():
    """Run quick benchmark."""
    print("=" * 80)
    print("Quick Gemini 3.1 Benchmark")
    print("=" * 80)
    print(f"\nStarted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Initialize clients with longer timeout for Pro
    medgemma = MedGemmaClient(model="google/medgemma-4b-it")
    gemini_flash = GeminiClient(model="gemini-3.1-flash-image-preview", use_vertex_ai=True, timeout=90)
    gemini_pro = GeminiClient(model="gemini-3.1-pro-preview", use_vertex_ai=True, timeout=120)

    print("Models:")
    print("  • MedGemma 4B (google/medgemma-4b-it)")
    print("  • Gemini 3.1 Flash Image Preview (Vertex AI, 90s timeout)")
    print("  • Gemini 3.1 Pro Preview (Vertex AI, 120s timeout)\n")

    # Test scenarios
    scenarios = [
        {
            "name": "ADR Detection - Statin Myopathy",
            "prompt": """Patient: 62yo started Atorvastatin 80mg 3 weeks ago.
Now reports: muscle pain, weakness, dark urine.

Is this an adverse drug reaction? What should be done?""",
            "system_instruction": "You are a clinical pharmacist.",
            "max_tokens": 1024,
        },
        {
            "name": "Drug Interaction - NSAID + ACE Inhibitor",
            "prompt": """Patient asks: "I take Lisinopril 10mg for blood pressure. Can I take ibuprofen for back pain?"

Patient: 55yo, hypertension (well-controlled), no kidney problems.""",
            "system_instruction": "You are a pharmacist counseling a patient.",
            "max_tokens": 1024,
        },
    ]

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'#' * 80}")
        print(f"Test {i}/{len(scenarios)}: {scenario['name']}")
        print(f"{'#' * 80}\n")

        # Test MedGemma
        print("Testing MedGemma 4B...")
        try:
            start = time.time()
            response = await medgemma.generate(
                prompt=scenario["prompt"],
                system_instruction=scenario["system_instruction"],
                temperature=0.7,
                max_tokens=scenario["max_tokens"],
            )
            elapsed = time.time() - start
            print(f"✅ Completed in {elapsed:.2f}s ({len(response)} chars, {len(response.split())} words)")
        except Exception as e:
            print(f"❌ Failed: {e}")

        # Test Gemini Flash
        print("\nTesting Gemini 3.1 Flash Image Preview...")
        try:
            start = time.time()
            response = await gemini_flash.generate(
                prompt=scenario["prompt"],
                system_instruction=scenario["system_instruction"],
                temperature=0.7,
                max_tokens=scenario["max_tokens"],
            )
            elapsed = time.time() - start
            print(f"✅ Completed in {elapsed:.2f}s ({len(response)} chars, {len(response.split())} words)")
        except Exception as e:
            print(f"❌ Failed: {e}")

        # Test Gemini Pro
        print("\nTesting Gemini 3.1 Pro Preview...")
        try:
            start = time.time()
            response = await gemini_pro.generate(
                prompt=scenario["prompt"],
                system_instruction=scenario["system_instruction"],
                temperature=0.7,
                max_tokens=scenario["max_tokens"],
            )
            elapsed = time.time() - start
            print(f"✅ Completed in {elapsed:.2f}s ({len(response)} chars, {len(response.split())} words)")
            print(f"\nResponse preview (first 200 chars):")
            print(response[:200] + "...")
        except Exception as e:
            print(f"❌ Failed: {e}")

        # Delay between tests
        if i < len(scenarios):
            await asyncio.sleep(3)

    print(f"\n{'=' * 80}")
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    asyncio.run(main())
