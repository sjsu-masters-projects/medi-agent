#!/usr/bin/env python3
"""Quick verification script for MedGemma setup.

This script checks that:
1. MedGemmaClient can be imported
2. Configuration is correct
3. Client initializes properly in both HF and fallback modes
"""

import sys
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

from app.clients.medgemma import MedGemmaClient
from app.config import settings


def main():
    """Run verification checks."""
    print("=" * 60)
    print("MedGemma Setup Verification")
    print("=" * 60)

    # Check 1: Import
    print("\n✅ Check 1: MedGemmaClient imports successfully")

    # Check 2: Configuration
    print("\n📋 Check 2: Configuration")
    if settings.huggingface_api_token:
        print(f"   ✅ HUGGINGFACE_API_TOKEN is set")
        print(f"   Token: {settings.huggingface_api_token[:10]}...")
    else:
        print(f"   ⚠️  HUGGINGFACE_API_TOKEN not set (will use Gemini fallback)")

    # Check 3: Client initialization with HF
    print("\n🔧 Check 3: Client Initialization")
    try:
        client_hf = MedGemmaClient(model="google/medgemma-4b-it")
        print(f"   ✅ MedGemmaClient initialized")
        print(f"   Model: {client_hf.model_name}")
        print(f"   Using HF API: {client_hf.use_hf}")
        if client_hf.use_hf:
            print(f"   API URL: {client_hf.api_url}")
    except Exception as e:
        print(f"   ❌ Failed to initialize: {e}")
        return

    # Check 4: Available models
    print("\n📦 Check 4: Available MedGemma Models")
    models = [
        "google/medgemma-1.5-4b-it (smallest, fastest)",
        "google/medgemma-4b-it (medium, recommended)",
        "google/medgemma-27b-it (largest, best quality)",
    ]
    for model in models:
        print(f"   • {model}")

    # Check 5: Interface compatibility
    print("\n🔌 Check 5: Interface Compatibility")
    methods = ["generate", "generate_structured", "generate_stream"]
    for method in methods:
        if hasattr(client_hf, method) and callable(getattr(client_hf, method)):
            print(f"   ✅ {method}() available")
        else:
            print(f"   ❌ {method}() missing")

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    if settings.huggingface_api_token:
        print("\n✅ MedGemma is ready to use with Hugging Face API!")
        print("\nNext steps:")
        print("1. Run: python backend/scripts/test_medgemma_hf.py")
        print("2. Compare responses with Gemini")
        print("3. Run benchmarks when ready")
    else:
        print("\n⚠️  MedGemma will use Gemini fallback")
        print("\nTo enable Hugging Face API:")
        print("1. Add HUGGINGFACE_API_TOKEN to .env")
        print("2. Get token from: https://huggingface.co/settings/tokens")
        print("3. Accept terms at: https://huggingface.co/google/medgemma-4b-it")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
