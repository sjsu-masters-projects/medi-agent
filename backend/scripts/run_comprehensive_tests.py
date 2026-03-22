#!/usr/bin/env python3
"""Comprehensive MedGemma testing with detailed reports.

This script runs extensive tests on MedGemma and generates detailed
comparison reports for different medical scenarios.

Usage:
    python backend/scripts/run_comprehensive_tests.py
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Add backend/src to path
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

from app.clients.gemini import GeminiClient
from app.clients.medgemma import MedGemmaClient
from app.config import settings


class TestResult:
    """Store test results."""

    def __init__(self, scenario: str, prompt: str):
        self.scenario = scenario
        self.prompt = prompt
        self.medgemma_response = None
        self.medgemma_time = 0
        self.medgemma_error = None
        self.gemini_response = None
        self.gemini_time = 0
        self.gemini_error = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scenario": self.scenario,
            "prompt": self.prompt,
            "medgemma": {
                "response": self.medgemma_response,
                "time_seconds": round(self.medgemma_time, 2),
                "error": self.medgemma_error,
                "success": self.medgemma_error is None,
            },
            "gemini": {
                "response": self.gemini_response,
                "time_seconds": round(self.gemini_time, 2),
                "error": self.gemini_error,
                "success": self.gemini_error is None,
            },
        }


async def test_scenario(
    scenario: str,
    prompt: str,
    medgemma_client: MedGemmaClient,
    gemini_client: GeminiClient | None,
    system_instruction: str | None = None,
    max_tokens: int = 1024,
) -> TestResult:
    """Test a single scenario with both models."""
    result = TestResult(scenario, prompt)

    print(f"\n{'=' * 80}")
    print(f"Scenario: {scenario}")
    print(f"{'=' * 80}")
    print(f"\nPrompt:\n{prompt[:200]}{'...' if len(prompt) > 200 else ''}\n")

    # Test MedGemma
    print("Testing MedGemma...")
    try:
        start = time.time()
        result.medgemma_response = await medgemma_client.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.7,
            max_tokens=max_tokens,
        )
        result.medgemma_time = time.time() - start
        print(f"✅ MedGemma completed in {result.medgemma_time:.2f}s")
        print(f"Response length: {len(result.medgemma_response)} chars")
    except Exception as e:
        result.medgemma_error = str(e)
        print(f"❌ MedGemma failed: {e}")

    # Test Gemini (if available)
    if gemini_client:
        print("Testing Gemini...")
        try:
            start = time.time()
            result.gemini_response = await gemini_client.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=0.7,
                max_tokens=max_tokens,
            )
            result.gemini_time = time.time() - start
            print(f"✅ Gemini completed in {result.gemini_time:.2f}s")
            print(f"Response length: {len(result.gemini_response)} chars")
        except Exception as e:
            result.gemini_error = str(e)
            print(f"❌ Gemini failed: {e}")
    else:
        print("⚠️  Gemini skipped (GOOGLE_API_KEY not set)")

    return result


async def main():
    """Run comprehensive tests."""
    print("=" * 80)
    print("MedGemma Comprehensive Testing & Benchmarking")
    print("=" * 80)
    print(f"\nStarted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Initialize clients
    medgemma = MedGemmaClient(model="google/medgemma-4b-it")
    gemini = None

    if settings.google_api_key:
        gemini = GeminiClient(model="gemini-2.0-flash-exp")
        print("✅ Both MedGemma and Gemini configured")
    else:
        print("⚠️  Only MedGemma configured (GOOGLE_API_KEY not set)")
        print("   Comparison with Gemini will be skipped\n")

    # Define test scenarios
    scenarios = [
        {
            "name": "Basic Medical Question - Diabetes Symptoms",
            "prompt": "What are the common symptoms of type 2 diabetes?",
            "system_instruction": None,
            "max_tokens": 512,
        },
        {
            "name": "Lab Result Explanation - Elevated WBC",
            "prompt": """Explain this lab result to a patient in simple, easy-to-understand terms:

White Blood Cell Count: 12.5 K/uL (normal range: 4.5-11.0 K/uL)

Patient context:
- Age: 65 years old
- Medical history: Type 2 diabetes, hypertension
- Current medications: Metformin 1000mg twice daily, Lisinopril 10mg once daily

Please explain what this result means and what the patient should do.""",
            "system_instruction": "You are a medical expert explaining lab results to patients. Use simple language, avoid medical jargon, and be reassuring while being accurate.",
            "max_tokens": 1024,
        },
        {
            "name": "Lab Result Explanation - Low Hemoglobin",
            "prompt": """Explain this lab result to a patient:

Hemoglobin: 11.2 g/dL (normal range for adult female: 12.0-16.0 g/dL)

Patient context:
- Age: 45 years old, female
- Symptoms: Fatigue, weakness
- No significant medical history

What does this mean and what should the patient do?""",
            "system_instruction": "You are a medical expert. Explain in patient-friendly language.",
            "max_tokens": 1024,
        },
        {
            "name": "Adverse Drug Reaction Detection - Statin Myopathy",
            "prompt": """A patient reports the following symptoms and medication history:

Symptoms:
- Muscle pain and weakness (started 2 weeks ago)
- Dark-colored urine
- Fatigue

Medication History:
- Started Atorvastatin 80mg daily (3 weeks ago for high cholesterol)
- No other new medications

Patient Information:
- Age: 62 years old
- Medical history: High cholesterol, no other conditions
- No recent injuries or unusual physical activity

Questions:
1. Is this likely an adverse drug reaction?
2. What is the suspected condition?
3. What should be done immediately?
4. Should the medication be stopped?""",
            "system_instruction": "You are a clinical pharmacist evaluating potential adverse drug reactions. Provide a thorough assessment.",
            "max_tokens": 1024,
        },
        {
            "name": "Adverse Drug Reaction Detection - ACE Inhibitor Cough",
            "prompt": """Patient report:

Symptoms:
- Persistent dry cough (started 1 week ago)
- No fever, no chest pain
- Cough is worse at night

Medication History:
- Started Lisinopril 10mg daily (2 weeks ago for hypertension)
- Previously on Amlodipine (switched due to ankle swelling)

Patient Information:
- Age: 58 years old
- No history of asthma or allergies
- Non-smoker

Is this an adverse drug reaction? What should be done?""",
            "system_instruction": "You are a clinical pharmacist. Evaluate this case for adverse drug reactions.",
            "max_tokens": 1024,
        },
        {
            "name": "Medication Question - Drug Interaction",
            "prompt": """A patient asks:

"I take Lisinopril 10mg once daily for high blood pressure. Can I take ibuprofen for my back pain? I've been taking it for a few days and want to make sure it's safe."

Patient context:
- Age: 55 years old
- Medications: Lisinopril 10mg daily
- Medical history: Hypertension (well-controlled)
- No kidney problems

Please provide a clear answer about this drug interaction.""",
            "system_instruction": "You are a pharmacist counseling a patient. Be clear about drug interactions and provide practical advice.",
            "max_tokens": 1024,
        },
        {
            "name": "Symptom Triage - Chest Pain (Emergency)",
            "prompt": """Patient presents with:

Symptoms:
- Chest pain (started 30 minutes ago)
- Pain radiating to left arm
- Shortness of breath
- Sweating
- Nausea

Patient Information:
- Age: 58 years old, male
- Medical history: Hypertension, high cholesterol
- Medications: Lisinopril, Atorvastatin
- Smoker (20 pack-years)

What is the urgency level and what should the patient do immediately?""",
            "system_instruction": "You are a triage nurse. Assess the urgency and provide clear action steps.",
            "max_tokens": 512,
        },
        {
            "name": "Symptom Triage - Mild Headache",
            "prompt": """Patient presents with:

Symptoms:
- Mild headache (started this morning)
- No fever
- No vision changes
- No neck stiffness

Patient Information:
- Age: 32 years old, female
- No significant medical history
- Slept poorly last night
- Stressed at work

What is the urgency level and what should the patient do?""",
            "system_instruction": "You are a triage nurse. Assess the urgency and provide guidance.",
            "max_tokens": 512,
        },
        {
            "name": "Discharge Summary Explanation",
            "prompt": """Explain this discharge summary to a patient in simple terms:

Admission Reason: Acute myocardial infarction (heart attack)

Procedures Performed:
- Cardiac catheterization
- Percutaneous coronary intervention (PCI) with stent placement in left anterior descending artery

New Medications:
1. Clopidogrel 75mg once daily (blood thinner)
2. Atorvastatin 80mg once daily (cholesterol medication)
3. Metoprolol 50mg twice daily (heart medication)
4. Aspirin 81mg once daily (blood thinner)

Follow-up:
- Cardiology appointment in 2 weeks
- Cardiac rehabilitation program

Activity Restrictions:
- No heavy lifting (>10 lbs) for 4 weeks
- No driving for 1 week
- Gradual return to activities as tolerated

Please explain what happened, what the medications are for, and what the patient needs to do.""",
            "system_instruction": "You are a nurse explaining a discharge summary to a patient. Use simple language and organize information clearly.",
            "max_tokens": 1536,
        },
        {
            "name": "Medical Concept Explanation - Hemoglobin A1C",
            "prompt": """A patient asks: "My doctor said my hemoglobin A1C is 7.2% and wants me to start medication. What is hemoglobin A1C and why does it matter?"

Please explain:
1. What hemoglobin A1C is
2. What the number means
3. Why it's important
4. What a normal range is""",
            "system_instruction": "You are a diabetes educator. Explain medical concepts in simple, patient-friendly language.",
            "max_tokens": 1024,
        },
    ]

    # Run tests
    results = []
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'#' * 80}")
        print(f"Test {i}/{len(scenarios)}")
        print(f"{'#' * 80}")

        result = await test_scenario(
            scenario=scenario["name"],
            prompt=scenario["prompt"],
            medgemma_client=medgemma,
            gemini_client=gemini,
            system_instruction=scenario.get("system_instruction"),
            max_tokens=scenario.get("max_tokens", 1024),
        )
        results.append(result)

        # Small delay to avoid rate limiting
        await asyncio.sleep(2)

    # Generate reports
    print("\n" + "=" * 80)
    print("Generating Reports...")
    print("=" * 80)

    # Save JSON report
    json_report_path = Path(__file__).parent.parent / "reports" / f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    json_report_path.parent.mkdir(exist_ok=True)

    json_data = {
        "timestamp": datetime.now().isoformat(),
        "models": {
            "medgemma": "google/medgemma-4b-it",
            "gemini": "gemini-2.0-flash-exp" if gemini else None,
        },
        "results": [r.to_dict() for r in results],
    }

    with open(json_report_path, "w") as f:
        json.dump(json_data, f, indent=2)

    print(f"\n✅ JSON report saved: {json_report_path}")

    # Generate markdown report
    md_report_path = json_report_path.with_suffix(".md")
    generate_markdown_report(results, md_report_path, gemini is not None)
    print(f"✅ Markdown report saved: {md_report_path}")

    # Print summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)

    medgemma_success = sum(1 for r in results if r.medgemma_error is None)
    medgemma_avg_time = sum(r.medgemma_time for r in results if r.medgemma_error is None) / max(medgemma_success, 1)

    print(f"\nMedGemma:")
    print(f"  Success: {medgemma_success}/{len(results)}")
    print(f"  Avg time: {medgemma_avg_time:.2f}s")

    if gemini:
        gemini_success = sum(1 for r in results if r.gemini_error is None)
        gemini_avg_time = sum(r.gemini_time for r in results if r.gemini_error is None) / max(gemini_success, 1)

        print(f"\nGemini:")
        print(f"  Success: {gemini_success}/{len(results)}")
        print(f"  Avg time: {gemini_avg_time:.2f}s")

        if medgemma_success > 0 and gemini_success > 0:
            speed_diff = ((medgemma_avg_time - gemini_avg_time) / gemini_avg_time) * 100
            if speed_diff > 0:
                print(f"\n⚡ Gemini is {abs(speed_diff):.1f}% faster on average")
            else:
                print(f"\n⚡ MedGemma is {abs(speed_diff):.1f}% faster on average")

    print("\n" + "=" * 80)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


def generate_markdown_report(results: list[TestResult], output_path: Path, has_gemini: bool):
    """Generate markdown report."""
    with open(output_path, "w") as f:
        f.write("# MedGemma Benchmarking Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Models Tested:**\n")
        f.write(f"- MedGemma: google/medgemma-4b-it\n")
        if has_gemini:
            f.write(f"- Gemini: gemini-2.0-flash-exp\n")
        f.write("\n---\n\n")

        # Summary table
        f.write("## Summary\n\n")
        f.write("| Metric | MedGemma | Gemini |\n")
        f.write("|--------|----------|--------|\n")

        medgemma_success = sum(1 for r in results if r.medgemma_error is None)
        medgemma_avg_time = sum(r.medgemma_time for r in results if r.medgemma_error is None) / max(medgemma_success, 1)

        if has_gemini:
            gemini_success = sum(1 for r in results if r.gemini_error is None)
            gemini_avg_time = sum(r.gemini_time for r in results if r.gemini_error is None) / max(gemini_success, 1)
            f.write(f"| Success Rate | {medgemma_success}/{len(results)} | {gemini_success}/{len(results)} |\n")
            f.write(f"| Avg Response Time | {medgemma_avg_time:.2f}s | {gemini_avg_time:.2f}s |\n")
        else:
            f.write(f"| Success Rate | {medgemma_success}/{len(results)} | N/A |\n")
            f.write(f"| Avg Response Time | {medgemma_avg_time:.2f}s | N/A |\n")

        f.write("\n---\n\n")

        # Detailed results
        f.write("## Detailed Results\n\n")

        for i, result in enumerate(results, 1):
            f.write(f"### {i}. {result.scenario}\n\n")

            f.write(f"**Prompt:**\n```\n{result.prompt}\n```\n\n")

            # MedGemma result
            f.write(f"#### MedGemma Response\n\n")
            if result.medgemma_error:
                f.write(f"❌ **Error:** {result.medgemma_error}\n\n")
            else:
                f.write(f"⏱️ **Time:** {result.medgemma_time:.2f}s\n\n")
                f.write(f"**Response:**\n```\n{result.medgemma_response}\n```\n\n")

            # Gemini result
            if has_gemini:
                f.write(f"#### Gemini Response\n\n")
                if result.gemini_error:
                    f.write(f"❌ **Error:** {result.gemini_error}\n\n")
                else:
                    f.write(f"⏱️ **Time:** {result.gemini_time:.2f}s\n\n")
                    f.write(f"**Response:**\n```\n{result.gemini_response}\n```\n\n")

                # Comparison
                if not result.medgemma_error and not result.gemini_error:
                    f.write(f"#### Comparison\n\n")
                    speed_diff = ((result.medgemma_time - result.gemini_time) / result.gemini_time) * 100
                    if speed_diff > 0:
                        f.write(f"- ⚡ Gemini was {abs(speed_diff):.1f}% faster\n")
                    else:
                        f.write(f"- ⚡ MedGemma was {abs(speed_diff):.1f}% faster\n")

                    len_diff = len(result.medgemma_response) - len(result.gemini_response)
                    if len_diff > 0:
                        f.write(f"- 📝 MedGemma response was {len_diff} chars longer\n")
                    elif len_diff < 0:
                        f.write(f"- 📝 Gemini response was {abs(len_diff)} chars longer\n")

                    f.write(f"\n💡 **Note:** Response quality should be evaluated by medical experts\n\n")

            f.write("---\n\n")

        # Recommendations
        f.write("## Recommendations\n\n")
        f.write("### Next Steps\n\n")
        f.write("1. **Medical Expert Review**\n")
        f.write("   - Have clinicians evaluate response accuracy\n")
        f.write("   - Check for medical errors or hallucinations\n")
        f.write("   - Assess patient comprehension\n\n")

        f.write("2. **Formal Benchmarking**\n")
        f.write("   - Create golden test sets with expert annotations\n")
        f.write("   - Measure accuracy, precision, recall\n")
        f.write("   - Calculate Flesch-Kincaid readability scores\n\n")

        f.write("3. **Cost Analysis**\n")
        f.write("   - Calculate cost per request\n")
        f.write("   - Project monthly costs at scale\n")
        f.write("   - Compare with Gemini pricing\n\n")

        f.write("4. **Model Selection Decision**\n")
        f.write("   - If MedGemma shows >10% accuracy improvement: Consider Vertex AI deployment\n")
        f.write("   - If Gemini is comparable: Stick with Gemini (faster, cheaper)\n")
        f.write("   - Re-evaluate as models improve\n\n")


if __name__ == "__main__":
    asyncio.run(main())
