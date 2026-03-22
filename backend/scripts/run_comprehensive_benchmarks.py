#!/usr/bin/env python3
"""Comprehensive benchmarking with quality analysis.

This script runs extensive tests comparing MedGemma vs Gemini Flash vs Gemini Pro
with automated quality metrics and detailed analysis.

Usage:
    python backend/scripts/run_comprehensive_benchmarks.py
"""

import asyncio
import json
import re
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


class QualityMetrics:
    """Calculate quality metrics for responses."""

    @staticmethod
    def flesch_reading_ease(text: str) -> float:
        """Calculate Flesch Reading Ease score (0-100, higher = easier)."""
        # Remove code blocks and special formatting
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'`[^`]+`', '', text)
        
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        words = re.findall(r'\b\w+\b', text)
        
        if not sentences or not words:
            return 0.0
        
        syllables = sum(QualityMetrics._count_syllables(word) for word in words)
        
        avg_sentence_length = len(words) / len(sentences)
        avg_syllables_per_word = syllables / len(words)
        
        score = 206.835 - 1.015 * avg_sentence_length - 84.6 * avg_syllables_per_word
        return max(0, min(100, score))

    @staticmethod
    def _count_syllables(word: str) -> int:
        """Count syllables in a word (simple approximation)."""
        word = word.lower()
        vowels = 'aeiouy'
        syllable_count = 0
        previous_was_vowel = False
        
        for char in word:
            is_vowel = char in vowels
            if is_vowel and not previous_was_vowel:
                syllable_count += 1
            previous_was_vowel = is_vowel
        
        if word.endswith('e'):
            syllable_count -= 1
        
        return max(1, syllable_count)

    @staticmethod
    def medical_term_density(text: str) -> float:
        """Calculate percentage of medical/technical terms."""
        medical_terms = [
            'myocardial', 'infarction', 'catheterization', 'percutaneous',
            'hemoglobin', 'leukocyte', 'thrombocytopenia', 'hypertension',
            'diabetes', 'cholesterol', 'atorvastatin', 'lisinopril',
            'pharmacovigilance', 'naranjo', 'adverse', 'reaction',
            'rhabdomyolysis', 'myopathy', 'hepatotoxicity', 'nephrotoxicity',
        ]
        
        words = re.findall(r'\b\w+\b', text.lower())
        if not words:
            return 0.0
        
        medical_count = sum(1 for word in words if word in medical_terms)
        return (medical_count / len(words)) * 100

    @staticmethod
    def has_actionable_advice(text: str) -> bool:
        """Check if response contains actionable advice."""
        action_patterns = [
            r'should\s+(see|contact|call|visit|consult)',
            r'(immediately|urgent|emergency)',
            r'(stop|discontinue|avoid)\s+\w+',
            r'follow.?up',
            r'(schedule|make)\s+an?\s+appointment',
        ]
        
        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in action_patterns)

    @staticmethod
    def has_safety_warnings(text: str) -> bool:
        """Check if response includes appropriate safety warnings."""
        warning_patterns = [
            r'(consult|see|contact)\s+(your\s+)?(doctor|physician|healthcare)',
            r'medical\s+(emergency|attention)',
            r'not\s+a\s+substitute',
            r'seek\s+(immediate|emergency)',
        ]
        
        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in warning_patterns)

    @staticmethod
    def response_completeness(text: str, expected_elements: list[str]) -> float:
        """Check if response covers expected elements."""
        text_lower = text.lower()
        covered = sum(1 for element in expected_elements if element.lower() in text_lower)
        return (covered / len(expected_elements)) * 100 if expected_elements else 0.0


class TestResult:
    """Store test results with quality metrics."""

    def __init__(self, scenario: str, prompt: str, expected_elements: list[str] = None):
        self.scenario = scenario
        self.prompt = prompt
        self.expected_elements = expected_elements or []
        
        # Model responses
        self.medgemma_response = None
        self.medgemma_time = 0
        self.medgemma_error = None
        
        self.gemini_flash_response = None
        self.gemini_flash_time = 0
        self.gemini_flash_error = None
        
        self.gemini_pro_response = None
        self.gemini_pro_time = 0
        self.gemini_pro_error = None

    def calculate_metrics(self):
        """Calculate quality metrics for all responses."""
        self.metrics = {}
        
        for model_name, response in [
            ("medgemma", self.medgemma_response),
            ("gemini_flash", self.gemini_flash_response),
            ("gemini_pro", self.gemini_pro_response),
        ]:
            if response:
                self.metrics[model_name] = {
                    "readability_score": round(QualityMetrics.flesch_reading_ease(response), 1),
                    "medical_term_density": round(QualityMetrics.medical_term_density(response), 1),
                    "has_actionable_advice": QualityMetrics.has_actionable_advice(response),
                    "has_safety_warnings": QualityMetrics.has_safety_warnings(response),
                    "completeness": round(QualityMetrics.response_completeness(response, self.expected_elements), 1),
                    "response_length": len(response),
                    "word_count": len(re.findall(r'\b\w+\b', response)),
                }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scenario": self.scenario,
            "prompt": self.prompt[:200] + "..." if len(self.prompt) > 200 else self.prompt,
            "medgemma": {
                "response": self.medgemma_response,
                "time_seconds": round(self.medgemma_time, 2),
                "error": self.medgemma_error,
                "success": self.medgemma_error is None,
                "metrics": self.metrics.get("medgemma") if hasattr(self, 'metrics') else None,
            },
            "gemini_flash": {
                "response": self.gemini_flash_response,
                "time_seconds": round(self.gemini_flash_time, 2),
                "error": self.gemini_flash_error,
                "success": self.gemini_flash_error is None,
                "metrics": self.metrics.get("gemini_flash") if hasattr(self, 'metrics') else None,
            },
            "gemini_pro": {
                "response": self.gemini_pro_response,
                "time_seconds": round(self.gemini_pro_time, 2),
                "error": self.gemini_pro_error,
                "success": self.gemini_pro_error is None,
                "metrics": self.metrics.get("gemini_pro") if hasattr(self, 'metrics') else None,
            },
        }


async def test_scenario(
    scenario: str,
    prompt: str,
    expected_elements: list[str],
    medgemma_client: MedGemmaClient,
    gemini_flash_client: GeminiClient | None,
    gemini_pro_client: GeminiClient | None,
    system_instruction: str | None = None,
    max_tokens: int = 1024,
) -> TestResult:
    """Test a single scenario with all models."""
    result = TestResult(scenario, prompt, expected_elements)

    print(f"\n{'=' * 80}")
    print(f"Scenario: {scenario}")
    print(f"{'=' * 80}\n")

    # Test MedGemma
    print("Testing MedGemma 4B...")
    try:
        start = time.time()
        result.medgemma_response = await medgemma_client.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.7,
            max_tokens=max_tokens,
        )
        result.medgemma_time = time.time() - start
        print(f"✅ Completed in {result.medgemma_time:.2f}s ({len(result.medgemma_response)} chars)")
    except Exception as e:
        result.medgemma_error = str(e)
        print(f"❌ Failed: {e}")

    # Test Gemini Flash
    if gemini_flash_client:
        print("Testing Gemini 3.1 Flash Image Preview...")
        try:
            start = time.time()
            result.gemini_flash_response = await gemini_flash_client.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=0.7,
                max_tokens=max_tokens,
            )
            result.gemini_flash_time = time.time() - start
            print(f"✅ Completed in {result.gemini_flash_time:.2f}s ({len(result.gemini_flash_response)} chars)")
        except Exception as e:
            result.gemini_flash_error = str(e)
            print(f"❌ Failed: {e}")
    else:
        print("⚠️  Gemini Flash skipped (GOOGLE_API_KEY not set)")

    # Test Gemini Pro
    if gemini_pro_client:
        print("Testing Gemini 3.1 Pro Preview...")
        try:
            start = time.time()
            result.gemini_pro_response = await gemini_pro_client.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=0.7,
                max_tokens=max_tokens,
            )
            result.gemini_pro_time = time.time() - start
            print(f"✅ Completed in {result.gemini_pro_time:.2f}s ({len(result.gemini_pro_response)} chars)")
        except Exception as e:
            result.gemini_pro_error = str(e)
            print(f"❌ Failed: {e}")
    else:
        print("⚠️  Gemini Pro skipped (GOOGLE_API_KEY not set)")

    # Calculate quality metrics
    result.calculate_metrics()

    return result


async def main():
    """Run comprehensive benchmarks."""
    print("=" * 80)
    print("MedGemma vs Gemini Comprehensive Benchmarking")
    print("=" * 80)
    print(f"\nStarted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Check API keys
    has_google_key = bool(settings.google_api_key)
    has_hf_token = bool(settings.huggingface_api_token)

    print("Configuration:")
    print(f"  Google API Key: {'✅ SET' if has_google_key else '❌ NOT SET'}")
    print(f"  HF API Token: {'✅ SET' if has_hf_token else '❌ NOT SET'}\n")

    if not has_google_key:
        print("⚠️  WARNING: GOOGLE_API_KEY not set")
        print("   Gemini comparison will be skipped")
        print("   See: backend/docs/API_KEYS_SETUP_GUIDE.md\n")

    if not has_hf_token:
        print("⚠️  WARNING: HUGGINGFACE_API_TOKEN not set")
        print("   MedGemma will fall back to Gemini")
        print("   See: backend/docs/API_KEYS_SETUP_GUIDE.md\n")

    # Initialize clients
    medgemma = MedGemmaClient(model="google/medgemma-4b-it")
    
    # Use Vertex AI for Gemini if project ID is configured
    # Using Gemini 3.1 preview models (require location="global")
    # Increase timeout for Pro model (it's very slow)
    use_vertex_ai = bool(settings.google_project_id)
    gemini_flash = GeminiClient(model="gemini-3.1-flash-image-preview", use_vertex_ai=use_vertex_ai, timeout=90) if has_google_key or use_vertex_ai else None
    gemini_pro = GeminiClient(model="gemini-3.1-pro-preview", use_vertex_ai=use_vertex_ai, timeout=120) if has_google_key or use_vertex_ai else None

    print("Models:")
    print("  • MedGemma 4B (google/medgemma-4b-it)")
    if gemini_flash or gemini_pro:
        mode = "Vertex AI" if use_vertex_ai else "AI Studio"
        print(f"  • Gemini 3.1 Flash Image Preview (latest multimodal) - {mode}")
        print(f"  • Gemini 3.1 Pro Preview (latest reasoning model) - {mode}\n")
    else:
        print("  • Gemini models: SKIPPED\n")

    # Define test scenarios with expected elements for completeness checking
    scenarios = [
        {
            "name": "Lab Result - Elevated WBC",
            "prompt": """Explain this lab result to a patient in simple terms:

White Blood Cell Count: 12.5 K/uL (normal: 4.5-11.0)

Patient: 65yo, diabetes, hypertension, on metformin and lisinopril.""",
            "system_instruction": "You are a medical expert. Use simple language.",
            "max_tokens": 512,
            "expected_elements": ["elevated", "infection", "inflammation", "doctor"],
        },
        {
            "name": "ADR Detection - Statin Myopathy",
            "prompt": """Patient: 62yo started Atorvastatin 80mg 3 weeks ago.
Now reports: muscle pain, weakness, dark urine.

Is this an adverse drug reaction? What should be done?""",
            "system_instruction": "You are a clinical pharmacist.",
            "max_tokens": 1024,
            "expected_elements": ["rhabdomyolysis", "stop", "ck", "doctor", "immediately"],
        },
        {
            "name": "Drug Interaction - NSAID + ACE Inhibitor",
            "prompt": """Patient asks: "I take Lisinopril 10mg for blood pressure. Can I take ibuprofen for back pain?"

Patient: 55yo, hypertension (well-controlled), no kidney problems.""",
            "system_instruction": "You are a pharmacist counseling a patient.",
            "max_tokens": 1024,
            "expected_elements": ["interaction", "kidney", "blood pressure", "acetaminophen", "doctor"],
        },
        {
            "name": "Emergency Triage - Chest Pain",
            "prompt": """Patient: 58yo male, smoker, hypertension, high cholesterol.

Symptoms (30 min ago): chest pain radiating to left arm, shortness of breath, sweating, nausea.

Urgency level and action?""",
            "system_instruction": "You are a triage nurse.",
            "max_tokens": 512,
            "expected_elements": ["emergency", "911", "heart attack", "immediately"],
        },
        {
            "name": "Discharge Summary Explanation",
            "prompt": """Explain to patient:

Admission: Heart attack
Procedures: Cardiac catheterization, stent placement
New meds: Clopidogrel 75mg, Atorvastatin 80mg, Metoprolol 50mg BID, Aspirin 81mg
Follow-up: Cardiology in 2 weeks, cardiac rehab
Restrictions: No heavy lifting (>10 lbs) for 4 weeks, no driving for 1 week""",
            "system_instruction": "You are a nurse. Use simple language.",
            "max_tokens": 1536,
            "expected_elements": ["heart attack", "stent", "blood thinner", "follow-up", "restrictions"],
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
            expected_elements=scenario["expected_elements"],
            medgemma_client=medgemma,
            gemini_flash_client=gemini_flash,
            gemini_pro_client=gemini_pro,
            system_instruction=scenario.get("system_instruction"),
            max_tokens=scenario.get("max_tokens", 1024),
        )
        results.append(result)

        # Delay to avoid rate limiting (increased for Gemini 3.1 models)
        await asyncio.sleep(10)

    # Generate reports
    print("\n" + "=" * 80)
    print("Generating Reports...")
    print("=" * 80)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    reports_dir = Path(__file__).parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    # JSON report
    json_path = reports_dir / f"benchmark_{timestamp}.json"
    json_data = {
        "timestamp": datetime.now().isoformat(),
        "models": {
            "medgemma": "google/medgemma-4b-it",
            "gemini_flash": "gemini-3.1-flash-image-preview" if has_google_key else None,
            "gemini_pro": "gemini-3.1-pro-preview" if has_google_key else None,
        },
        "results": [r.to_dict() for r in results],
    }

    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)

    print(f"\n✅ JSON report: {json_path}")

    # Markdown report
    md_path = json_path.with_suffix(".md")
    generate_markdown_report(results, md_path, has_google_key)
    print(f"✅ Markdown report: {md_path}")

    # Print summary
    print_summary(results, has_google_key)


def generate_markdown_report(results: list[TestResult], output_path: Path, has_gemini: bool):
    """Generate detailed markdown report."""
    with open(output_path, "w") as f:
        f.write("# MedGemma vs Gemini Benchmarking Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## Models Tested\n\n")
        f.write("- **MedGemma 4B:** google/medgemma-4b-it (medical-specialized)\n")
        if has_gemini:
            f.write("- **Gemini 3.1 Flash Image Preview:** Latest multimodal model with image capabilities\n")
            f.write("- **Gemini 3.1 Pro Preview:** Latest reasoning-first model for complex tasks\n")
        f.write("\n---\n\n")

        # Summary table
        f.write("## Performance Summary\n\n")
        f.write("| Metric | MedGemma 4B | Gemini Flash | Gemini Pro |\n")
        f.write("|--------|-------------|--------------|------------|\n")

        # Calculate averages
        models = ["medgemma", "gemini_flash", "gemini_pro"]
        for metric_name, metric_key in [
            ("Success Rate", "success"),
            ("Avg Response Time", "time"),
            ("Avg Readability", "readability"),
            ("Avg Completeness", "completeness"),
        ]:
            row = [metric_name]
            for model in models:
                if model == "gemini_flash" and not has_gemini:
                    row.append("N/A")
                elif model == "gemini_pro" and not has_gemini:
                    row.append("N/A")
                else:
                    if metric_key == "success":
                        count = sum(1 for r in results if getattr(r, f"{model}_error") is None)
                        row.append(f"{count}/{len(results)}")
                    elif metric_key == "time":
                        times = [getattr(r, f"{model}_time") for r in results if getattr(r, f"{model}_error") is None]
                        avg = sum(times) / len(times) if times else 0
                        row.append(f"{avg:.2f}s")
                    elif metric_key == "readability":
                        scores = [r.metrics.get(model, {}).get("readability_score", 0) for r in results if hasattr(r, 'metrics') and r.metrics.get(model)]
                        avg = sum(scores) / len(scores) if scores else 0
                        row.append(f"{avg:.1f}")
                    elif metric_key == "completeness":
                        scores = [r.metrics.get(model, {}).get("completeness", 0) for r in results if hasattr(r, 'metrics') and r.metrics.get(model)]
                        avg = sum(scores) / len(scores) if scores else 0
                        row.append(f"{avg:.1f}%")
            f.write("| " + " | ".join(row) + " |\n")

        f.write("\n---\n\n")

        # Detailed results
        f.write("## Detailed Results\n\n")

        for i, result in enumerate(results, 1):
            f.write(f"### {i}. {result.scenario}\n\n")
            f.write(f"**Prompt:** {result.prompt[:200]}{'...' if len(result.prompt) > 200 else ''}\n\n")

            # Results for each model
            for model_name, display_name in [
                ("medgemma", "MedGemma 4B"),
                ("gemini_flash", "Gemini 3.1 Flash Image Preview"),
                ("gemini_pro", "Gemini 3.1 Pro Preview"),
            ]:
                if model_name != "medgemma" and not has_gemini:
                    continue

                f.write(f"#### {display_name}\n\n")

                error = getattr(result, f"{model_name}_error")
                if error:
                    f.write(f"❌ **Error:** {error}\n\n")
                else:
                    response = getattr(result, f"{model_name}_response")
                    response_time = getattr(result, f"{model_name}_time")
                    metrics = result.metrics.get(model_name, {})

                    f.write(f"⏱️ **Time:** {response_time:.2f}s\n\n")

                    if metrics:
                        f.write(f"**Quality Metrics:**\n")
                        f.write(f"- Readability Score: {metrics['readability_score']}/100 ")
                        f.write(f"({'Easy' if metrics['readability_score'] > 60 else 'Moderate' if metrics['readability_score'] > 30 else 'Difficult'})\n")
                        f.write(f"- Completeness: {metrics['completeness']}%\n")
                        f.write(f"- Actionable Advice: {'✅ Yes' if metrics['has_actionable_advice'] else '❌ No'}\n")
                        f.write(f"- Safety Warnings: {'✅ Yes' if metrics['has_safety_warnings'] else '❌ No'}\n")
                        f.write(f"- Word Count: {metrics['word_count']}\n\n")

                    f.write(f"**Response:**\n```\n{response}\n```\n\n")

            f.write("---\n\n")


def print_summary(results: list[TestResult], has_gemini: bool):
    """Print summary to console."""
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)

    for model_name, display_name in [
        ("medgemma", "MedGemma 4B"),
        ("gemini_flash", "Gemini 3.1 Flash Image Preview"),
        ("gemini_pro", "Gemini 3.1 Pro Preview"),
    ]:
        if model_name != "medgemma" and not has_gemini:
            continue

        success = sum(1 for r in results if getattr(r, f"{model_name}_error") is None)
        times = [getattr(r, f"{model_name}_time") for r in results if getattr(r, f"{model_name}_error") is None]
        avg_time = sum(times) / len(times) if times else 0

        readability_scores = [r.metrics.get(model_name, {}).get("readability_score", 0) for r in results if hasattr(r, 'metrics') and r.metrics.get(model_name)]
        avg_readability = sum(readability_scores) / len(readability_scores) if readability_scores else 0

        completeness_scores = [r.metrics.get(model_name, {}).get("completeness", 0) for r in results if hasattr(r, 'metrics') and r.metrics.get(model_name)]
        avg_completeness = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0

        print(f"\n{display_name}:")
        print(f"  Success: {success}/{len(results)}")
        print(f"  Avg Time: {avg_time:.2f}s")
        print(f"  Avg Readability: {avg_readability:.1f}/100")
        print(f"  Avg Completeness: {avg_completeness:.1f}%")

    print("\n" + "=" * 80)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print("\n📊 Reports saved in backend/reports/")
    print("\n💡 Next Steps:")
    print("   1. Review markdown report for detailed comparison")
    print("   2. Have medical experts evaluate response accuracy")
    print("   3. Check for hallucinations or medical errors")
    print("   4. Make model selection decision based on results")
    print()


if __name__ == "__main__":
    asyncio.run(main())
