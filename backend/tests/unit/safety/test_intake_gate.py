from app.safety import TRIAGE_COPY, SafetyVerdict
from app.safety.intake_gate import evaluate_intake_safety, safety_response


def test_no_match_is_not_an_inferred_severity_or_negative_red_flag():
    assert evaluate_intake_safety("I have a mild headache", "en-US") is None
    assert evaluate_intake_safety("I do not have chest pain", "en-US") is None


def test_shared_gate_preserves_self_harm_precedence_and_reviewed_locale():
    result = evaluate_intake_safety("Tengo dolor de pecho y quiero morir", "es-MX")
    assert result is not None
    assert result.verdict.safety_rule == "emergency_mental_health_keyword"
    assert result.response_text == TRIAGE_COPY["es-MX"]["mental_health_emergency_response"]
    assert result.rule_version == "triage-floor/1"


def test_unmapped_rule_still_uses_reviewed_emergency_direction():
    verdict = SafetyVerdict("symptom", "emergency", "Synthetic rule", "synthetic_unknown")
    assert safety_response(verdict, "es-MX") == TRIAGE_COPY["es-MX"]["emergency_response"]
