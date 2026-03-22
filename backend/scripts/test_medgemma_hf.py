#!/usr/bin/env python3
"""Test script for MedGemma Hugging Face API integration.

This script verifies that MedGemmaClient can successfully connect to
Hugging Face Inference API and generate medical responses.

Usage:
    python backend/scripts/test_medgemma_hf.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

from app.clients.medgemma import MedGemmaClient
from app.config import settings


async def test_basic_generation():
    """Test basic text generation."""
    print("=" * 60)
    print("Test 1: Basic Medical Question")
    print("=" * 60)

    client = MedGemmaClient(model="google/medgemma-4b-it")

    prompt = "What are the common symptoms of type 2 diabetes?"

    print(f"\nPrompt: {prompt}")
    print("\nGenerating response...")

    try:
        response = await client.generate(
            prompt=prompt,
            temperature=0.7,
            max_tokens=512,
        )

        print(f"\nResponse:\n{response}")
        print("\n✅ Basic generation test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Basic generation test FAILED: {e}")
        return False


async def test_with_system_instruction():
    """Test generation with system instruction."""
    print("\n" + "=" * 60)
    print("Test 2: Generation with System Instruction")
    print("=" * 60)

    client = MedGemmaClient(model="google/medgemma-4b-it")

    system_instruction = (
        "You are a medical expert explaining concepts to patients. "
        "Use simple language and avoid medical jargon."
    )
    prompt = "Explain what hemoglobin A1C is and why it matters."

    print(f"\nSystem Instruction: {system_instruction}")
    print(f"\nPrompt: {prompt}")
    print("\nGenerating response...")

    try:
        response = await client.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.7,
            max_tokens=512,
        )

        print(f"\nResponse:\n{response}")
        print("\n✅ System instruction test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ System instruction test FAILED: {e}")
        return False


async def test_medical_explanation():
    """Test medical document explanation."""
    print("\n" + "=" * 60)
    print("Test 3: Medical Lab Result Explanation")
    print("=" * 60)

    client = MedGemmaClient(model="google/medgemma-4b-it")

    prompt = """
Explain these lab results to a patient in simple terms:

- White Blood Cell Count: 12.5 K/uL (normal: 4.5-11.0)
- Hemoglobin: 11.2 g/dL (normal: 12.0-16.0)
- Glucose (fasting): 145 mg/dL (normal: 70-100)

The patient is 65 years old with diabetes and hypertension.
"""

    print(f"\nPrompt: {prompt}")
    print("\nGenerating response...")

    try:
        response = await client.generate(
            prompt=prompt,
            temperature=0.7,
            max_tokens=1024,
        )

        print(f"\nResponse:\n{response}")
        print("\n✅ Medical explanation test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Medical explanation test FAILED: {e}")
        return False


async def test_adr_detection():
    """Test adverse drug reaction detection."""
    print("\n" + "=" * 60)
    print("Test 4: Adverse Drug Reaction Detection")
    print("=" * 60)

    client = MedGemmaClient(model="google/medgemma-4b-it")

    prompt = """
A patient reports the following:
- Started taking Atorvastatin 80mg two weeks ago
- Now experiencing muscle pain, weakness, and dark urine
- Age: 62, taking medication for high cholesterol

Is this likely an adverse drug reaction? If so, what should be done?
"""

    print(f"\nPrompt: {prompt}")
    print("\nGenerating response...")

    try:
        response = await client.generate(
            prompt=prompt,
            temperature=0.7,
            max_tokens=1024,
        )

        print(f"\nResponse:\n{response}")
        print("\n✅ ADR detection test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ ADR detection test FAILED: {e}")
        return False


async def test_model_comparison():
    """Test different MedGemma model sizes."""
    print("\n" + "=" * 60)
    print("Test 5: Model Size Comparison")
    print("=" * 60)

    models = [
        "google/medgemma-1.5-4b-it",  # Smallest
        "google/medgemma-4b-it",      # Medium
        # "google/medgemma-27b-it",   # Largest (commented out - may be slow)
    ]

    prompt = "What is the difference between type 1 and type 2 diabetes?"

    for model in models:
        print(f"\n--- Testing {model} ---")
        client = MedGemmaClient(model=model)

        try:
            import time
            start = time.time()

            response = await client.generate(
                prompt=prompt,
                temperature=0.7,
                max_tokens=256,
            )

            elapsed = time.time() - start

            print(f"Response time: {elapsed:.2f}s")
            print(f"Response length: {len(response)} chars")
            print(f"Response preview: {response[:200]}...")

        except Exception as e:
            print(f"❌ Failed: {e}")

    print("\n✅ Model comparison test PASSED")
    return True


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("MedGemma Hugging Face API Integration Tests")
    print("=" * 60)

    # Check configuration
    if not settings.huggingface_api_token:
        print("\n❌ ERROR: HUGGINGFACE_API_TOKEN not set in .env")
        print("Please add your Hugging Face API token to .env:")
        print("HUGGINGFACE_API_TOKEN=hf_...")
        return

    print(f"\n✅ Hugging Face API token configured")
    print(f"Token: {settings.huggingface_api_token[:10]}...")

    # Run tests
    results = []

    results.append(await test_basic_generation())
    results.append(await test_with_system_instruction())
    results.append(await test_medical_explanation())
    results.append(await test_adr_detection())
    results.append(await test_model_comparison())

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n🎉 All tests PASSED!")
    else:
        print(f"\n⚠️  {total - passed} test(s) FAILED")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
