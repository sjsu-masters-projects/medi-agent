#!/usr/bin/env python3
"""Compare MedGemma vs Gemini on medical reasoning tasks.

This script demonstrates A/B testing between MedGemma and Gemini
on the same medical prompts to compare response quality.

Usage:
    python backend/scripts/compare_medgemma_gemini.py
"""

import asyncio
import sys
import time
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

from app.clients.gemini import GeminiClient
from app.clients.medgemma import MedGemmaClient
from app.config import settings


async def compare_on_prompt(prompt: str, description: str):
    """Compare MedGemma and Gemini on a single prompt."""
    print("\n" + "=" * 80)
    print(f"Test: {description}")
    print("=" * 80)
    print(f"\nPrompt:\n{prompt}\n")

    # Initialize clients
    medgemma = MedGemmaClient(model="google/medgemma-4b-it")
    gemini = GeminiClient(model="gemini-2.0-flash-exp")

    # Test MedGemma
    print("-" * 80)
    print("MedGemma Response:")
    print("-" * 80)
    try:
        start = time.time()
        medgemma_response = await medgemma.generate(
            prompt=prompt,
            temperature=0.7,
            max_tokens=512,
        )
        medgemma_time = time.time() - start

        print(medgemma_response)
        print(f"\n⏱️  Response time: {medgemma_time:.2f}s")
        print(f"📏 Response length: {len(medgemma_response)} chars")

    except Exception as e:
        print(f"❌ Error: {e}")
        medgemma_response = None
        medgemma_time = 0

    # Test Gemini
    print("\n" + "-" * 80)
    print("Gemini Response:")
    print("-" * 80)
    try:
        start = time.time()
        gemini_response = await gemini.generate(
            prompt=prompt,
            temperature=0.7,
            max_tokens=512,
        )
        gemini_time = time.time() - start

        print(gemini_response)
        print(f"\n⏱️  Response time: {gemini_time:.2f}s")
        print(f"📏 Response length: {len(gemini_response)} chars")

    except Exception as e:
        print(f"❌ Error: {e}")
        gemini_response = None
        gemini_time = 0

    # Comparison
    print("\n" + "-" * 80)
    print("Comparison:")
    print("-" * 80)

    if medgemma_response and gemini_response:
        if medgemma_time > 0 and gemini_time > 0:
            speed_diff = ((medgemma_time - gemini_time) / gemini_time) * 100
            if speed_diff > 0:
                print(f"⚡ Gemini is {abs(speed_diff):.1f}% faster")
            else:
                print(f"⚡ MedGemma is {abs(speed_diff):.1f}% faster")

        length_diff = len(medgemma_response) - len(gemini_response)
        if length_diff > 0:
            print(f"📝 MedGemma response is {length_diff} chars longer")
        elif length_diff < 0:
            print(f"📝 Gemini response is {abs(length_diff)} chars longer")
        else:
            print(f"📝 Both responses are the same length")

        print("\n💡 Note: Response quality should be evaluated by medical experts")


async def main():
    """Run comparison tests."""
    print("=" * 80)
    print("MedGemma vs Gemini Comparison")
    print("=" * 80)

    # Check configuration
    if not settings.huggingface_api_token:
        print("\n❌ ERROR: HUGGINGFACE_API_TOKEN not set")
        print("MedGemma will fall back to Gemini (no real comparison)")
        print("\nTo enable MedGemma:")
        print("1. Add HUGGINGFACE_API_TOKEN to .env")
        print("2. Get token from: https://huggingface.co/settings/tokens")
        return

    if not settings.google_api_key:
        print("\n❌ ERROR: GOOGLE_API_KEY not set")
        print("Cannot test Gemini")
        return

    print("\n✅ Both API keys configured")

    # Test cases
    test_cases = [
        {
            "description": "Basic Medical Question",
            "prompt": "What are the common symptoms of type 2 diabetes?",
        },
        {
            "description": "Lab Result Explanation",
            "prompt": """
Explain this lab result to a patient in simple terms:

White Blood Cell Count: 12.5 K/uL (normal range: 4.5-11.0)

The patient is 65 years old with diabetes and hypertension.
""",
        },
        {
            "description": "Adverse Drug Reaction Detection",
            "prompt": """
A patient reports:
- Started Atorvastatin 80mg two weeks ago
- Now experiencing muscle pain, weakness, and dark urine
- Age: 62, taking medication for high cholesterol

Is this likely an adverse drug reaction? What should be done?
""",
        },
        {
            "description": "Medication Question",
            "prompt": """
Can I take ibuprofen with my blood pressure medication (Lisinopril 10mg)?
""",
        },
    ]

    # Run comparisons
    for test_case in test_cases:
        await compare_on_prompt(
            prompt=test_case["prompt"],
            description=test_case["description"],
        )

    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print("\n✅ Comparison complete!")
    print("\nNext steps:")
    print("1. Review responses for medical accuracy")
    print("2. Have medical experts evaluate quality")
    print("3. Run formal benchmarks with golden test sets")
    print("4. Measure accuracy, hallucination rate, and patient comprehension")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
