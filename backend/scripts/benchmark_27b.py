#!/usr/bin/env python3
"""MedGemma 27B vs Gemini Flash vs Gemini Pro — constrained benchmark.

Runs 5 medical scenarios with properly constrained prompts (max_tokens,
output format instructions) so that all three models produce comparable
responses.

Usage:
    cd backend
    python3 scripts/benchmark_27b.py
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from textwrap import dedent

# Add backend/src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "placeholder")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "placeholder")
os.environ.setdefault("SUPABASE_JWT_SECRET", "placeholder")

# ──────────────────────────────────────────────
# Scenarios — each has a prompt + system instruction
# ──────────────────────────────────────────────

SCENARIOS = [
    {
        "name": "Lab Result Explanation",
        "system": dedent(
            """\
            You are a nurse explaining lab results to a patient.
            Rules:
            - Use simple, non-technical language a 5th grader could understand.
            - Keep your response under 250 words.
            - Structure: What it is → Why it matters → What happens next.
            - Do NOT include any code, markdown tables, or JSON.
            - Do NOT repeat yourself."""
        ),
        "prompt": dedent("""\
            Explain this lab result to a patient in simple terms:

            White Blood Cell Count: 12.5 K/uL (normal: 4.5-11.0)

            Patient: 65yo, diabetes, hypertension, on metformin and lisinopril."""),
    },
    {
        "name": "ADR Detection — Statin Myopathy",
        "system": dedent(
            """\
            You are a clinical pharmacist assessing an adverse drug reaction.
            Rules:
            - Answer in 200-300 words.
            - Structure: Assessment → Immediate Action → Follow-up.
            - Include a Naranjo score estimate (1-10).
            - Do NOT include code snippets or repeat your answer.
            - Be direct and clinical."""
        ),
        "prompt": dedent("""\
            Patient: 62yo started Atorvastatin 80mg 3 weeks ago.
            Now reports: muscle pain, weakness, dark urine.

            Is this an adverse drug reaction? What should be done?"""),
    },
    {
        "name": "Drug Interaction — NSAID + ACE Inhibitor",
        "system": dedent(
            """\
            You are a pharmacist counseling a patient at the pharmacy counter.
            Rules:
            - Speak directly to the patient in a warm, conversational tone.
            - Keep your response under 200 words.
            - Give a clear yes/no answer first, then explain why.
            - Suggest one specific alternative.
            - Do NOT include code, disclaimers, or documentation references."""
        ),
        "prompt": dedent("""\
            Patient asks: "I take Lisinopril 10mg for blood pressure. Can I take ibuprofen for back pain?"

            Patient: 55yo, hypertension (well-controlled), no kidney problems."""),
    },
    {
        "name": "Emergency Triage — Chest Pain",
        "system": dedent("""\
            You are a triage nurse on a phone hotline.
            Rules:
            - Lead with the urgency level (use ESI scale 1-5).
            - Give 3-4 immediate action steps, numbered.
            - Keep response under 200 words.
            - Be calm but firm — this is a potential emergency.
            - Do NOT write code or repeat yourself."""),
        "prompt": dedent("""\
            Patient: 58yo male, smoker, hypertension, high cholesterol.

            Symptoms (30 min ago): chest pain radiating to left arm, shortness of breath, sweating, nausea.

            Urgency level and action?"""),
    },
    {
        "name": "Discharge Summary Explanation",
        "system": dedent("""\
            You are a nurse explaining discharge instructions to a patient and their family.
            Rules:
            - Use simple language.
            - Cover: What happened → Your new medications → Activity restrictions → Follow-up appointments.
            - Keep response under 350 words.
            - Do NOT include code, JSON, or medical jargon without explanation.
            - Do NOT repeat any section."""),
        "prompt": dedent("""\
            Explain to patient:

            Admission: Heart attack
            Procedures: Cardiac catheterization, stent placement
            New meds: Clopidogrel 75mg, Atorvastatin 80mg, Metoprolol 50mg BID, Aspirin 81mg
            Follow-up: Cardiology in 2 weeks, cardiac rehab
            Restrictions: No heavy lifting (>10 lbs) for 4 weeks, no driving for 1 week"""),
    },
]


# ──────────────────────────────────────────────
# Metrics helpers
# ──────────────────────────────────────────────

def count_words(text: str) -> int:
    """Count the number of words in a text string."""
    return len(text.split())


def readability_score(text: str) -> float:
    """Simplified Flesch reading ease (approximate)."""
    words = text.split()
    sentences = max(text.count(".") + text.count("!") + text.count("?"), 1)
    syllables = sum(max(1, len([c for c in w if c in "aeiouAEIOU"])) for w in words)
    if len(words) == 0:
        return 0.0
    return 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syllables / len(words))


def has_code_leak(text: str) -> bool:
    """Check if LLM leaked code into the response."""
    indicators = ["```", "def ", "import ", "print(", "class ", "return ", "lambda "]
    return any(ind in text for ind in indicators)


def has_repetition(text: str) -> bool:
    """Check if substantial paragraphs are repeated."""
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 50]
    seen = set()
    for p in paragraphs:
        normalized = p[:100].lower()
        if normalized in seen:
            return True
        seen.add(normalized)
    return False


def assess_completeness(text: str, scenario_name: str) -> int:
    """Score completeness 0-100 based on expected content markers."""
    markers = {
        "Lab Result Explanation": [
            "white blood cell", "immune", "infection", "normal", "next",
        ],
        "ADR Detection — Statin Myopathy": [
            "rhabdomyolysis", "stop", "CK", "kidney", "emergency",
        ],
        "Drug Interaction — NSAID + ACE Inhibitor": [
            "avoid", "kidney", "blood pressure", "acetaminophen", "alternative",
        ],
        "Emergency Triage — Chest Pain": [
            "911", "heart attack", "aspirin", "emergency", "immediate",
        ],
        "Discharge Summary Explanation": [
            "stent", "clopidogrel", "atorvastatin", "metoprolol", "rehab",
        ],
    }
    expected = markers.get(scenario_name, [])
    if not expected:
        return 50
    found = sum(1 for m in expected if m.lower() in text.lower())
    return int((found / len(expected)) * 100)


# ──────────────────────────────────────────────
# Model runners
# ──────────────────────────────────────────────

async def run_medgemma(scenario: dict) -> dict:
    """Run scenario through MedGemma 27B."""
    from app.clients.medgemma import MedGemmaClient

    client = MedGemmaClient(model="google/medgemma-27b-it")

    start = time.time()
    try:
        response = await client.generate(
            prompt=scenario["prompt"],
            system_instruction=scenario["system"],
            temperature=0.3,
            max_tokens=1024,
        )
        elapsed = time.time() - start
        return {
            "model": "MedGemma 27B",
            "response": response,
            "time_s": round(elapsed, 2),
            "error": None,
        }
    except Exception as e:
        return {
            "model": "MedGemma 27B",
            "response": "",
            "time_s": round(time.time() - start, 2),
            "error": str(e),
        }


async def run_gemini_flash(scenario: dict) -> dict:
    """Run scenario through Gemini Flash."""
    from app.clients.gemini import GeminiClient

    client = GeminiClient(model="gemini-3.1-flash-lite-preview", use_vertex_ai=True)

    start = time.time()
    try:
        response = await client.generate(
            prompt=scenario["prompt"],
            system_instruction=scenario["system"],
            temperature=0.3,
            max_tokens=1024,
        )
        elapsed = time.time() - start
        return {
            "model": "Gemini 3.1 Flash Lite",
            "response": response,
            "time_s": round(elapsed, 2),
            "error": None,
        }
    except Exception as e:
        return {
            "model": "Gemini 3.1 Flash Lite",
            "response": "",
            "time_s": round(time.time() - start, 2),
            "error": str(e),
        }


async def run_gemini_pro(scenario: dict) -> dict:
    """Run scenario through Gemini Pro."""
    from app.clients.gemini import GeminiClient

    client = GeminiClient(model="gemini-3.1-pro-preview", use_vertex_ai=True)

    start = time.time()
    try:
        response = await client.generate(
            prompt=scenario["prompt"],
            system_instruction=scenario["system"],
            temperature=0.3,
            max_tokens=1024,
        )
        elapsed = time.time() - start
        return {
            "model": "Gemini 3.1 Pro",
            "response": response,
            "time_s": round(elapsed, 2),
            "error": None,
        }
    except Exception as e:
        return {
            "model": "Gemini 3.1 Pro",
            "response": "",
            "time_s": round(time.time() - start, 2),
            "error": str(e),
        }


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

async def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = Path(__file__).resolve().parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    all_results = []

    print("=" * 70)
    print("MedGemma 27B vs Gemini Flash vs Gemini Pro — Benchmark")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"\n{'─' * 70}")
        print(f"Scenario {i}/5: {scenario['name']}")
        print(f"{'─' * 70}")

        scenario_results = {"scenario": scenario["name"], "models": []}

        # Run all 3 models sequentially (to avoid rate limits)
        for runner, label in [
            (run_medgemma, "MedGemma 27B"),
            (run_gemini_flash, "Gemini Flash"),
            (run_gemini_pro, "Gemini Pro"),
        ]:
            print(f"\n  ▸ Running {label}...", end=" ", flush=True)
            result = await runner(scenario)

            if result["error"]:
                print(f"❌ Error: {result['error'][:80]}")
            else:
                wc = count_words(result["response"])
                print(f"✅ {result['time_s']}s, {wc} words")

            # Compute metrics
            if result["response"]:
                result["metrics"] = {
                    "word_count": count_words(result["response"]),
                    "readability": round(readability_score(result["response"]), 1),
                    "completeness": assess_completeness(result["response"], scenario["name"]),
                    "has_code_leak": has_code_leak(result["response"]),
                    "has_repetition": has_repetition(result["response"]),
                }
            else:
                result["metrics"] = None

            scenario_results["models"].append(result)

        all_results.append(scenario_results)

    # ── Generate Reports ──

    # JSON report
    json_path = reports_dir / f"benchmark_27b_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # Markdown report
    md_path = reports_dir / f"benchmark_27b_{timestamp}.md"
    with open(md_path, "w") as f:
        f.write(f"# MedGemma 27B vs Gemini — Benchmark Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"**Prompts:** Properly constrained (max_tokens=1024, temp=0.3, output format rules)\n\n")
        f.write("---\n\n")

        # Summary table
        f.write("## Summary\n\n")
        f.write("| Scenario | MedGemma 27B | Gemini Flash | Gemini Pro |\n")
        f.write("|----------|-------------|-------------|------------|\n")
        for r in all_results:
            row = f"| {r['scenario']} |"
            for m in r["models"]:
                if m["error"]:
                    row += f" ❌ Error |"
                else:
                    met = m["metrics"]
                    code = "⚠️" if met["has_code_leak"] else "✅"
                    row += f" {m['time_s']}s, {met['word_count']}w, {met['completeness']}% {code} |"
            f.write(row + "\n")

        f.write("\n---\n\n")

        # Detailed results
        for r in all_results:
            f.write(f"## {r['scenario']}\n\n")
            for m in r["models"]:
                f.write(f"### {m['model']}\n\n")
                if m["error"]:
                    f.write(f"❌ **Error:** {m['error']}\n\n")
                else:
                    met = m["metrics"]
                    f.write(f"⏱️ **Time:** {m['time_s']}s | ")
                    f.write(f"📝 **Words:** {met['word_count']} | ")
                    f.write(f"📊 **Completeness:** {met['completeness']}% | ")
                    f.write(f"📖 **Readability:** {met['readability']} | ")
                    f.write(f"🔒 **Code leak:** {'YES ⚠️' if met['has_code_leak'] else 'No ✅'} | ")
                    f.write(f"🔄 **Repetition:** {'YES ⚠️' if met['has_repetition'] else 'No ✅'}\n\n")
                    f.write(f"**Response:**\n\n```\n{m['response']}\n```\n\n")
            f.write("---\n\n")

    print(f"\n{'=' * 70}")
    print(f"✅ Benchmark complete!")
    print(f"   JSON: {json_path}")
    print(f"   Report: {md_path}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
