import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "publish_symptom_questions.py"
spec = importlib.util.spec_from_file_location("publish_symptom_questions", SCRIPT)
assert spec and spec.loader
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

RELEASE = {"version": "v2", "hash": "a" * 64, "approval": {"reference": "r"}}


def database(*matches: bool) -> MagicMock:
    db = MagicMock()
    responses = iter(matches)

    def rpc(name, _params):
        call = MagicMock()
        if name == "symptom_intake_readiness":
            call.execute.return_value.data = {"eligibility_matches": next(responses)}
        return call

    db.rpc.side_effect = rpc
    return db


def names(db: MagicMock) -> list[str]:
    return [call.args[0] for call in db.rpc.call_args_list]


def test_dry_run_changes_nothing():
    db = database(False)
    assert publisher.run(db, RELEASE, apply=False) == 0
    assert "set_symptom_question_eligibility" not in names(db)


def test_apply_publishes_then_verifies():
    db = database(False, True)
    assert publisher.run(db, RELEASE, apply=True) == 0
    assert names(db) == [
        "symptom_intake_readiness",
        "set_symptom_question_eligibility",
        "symptom_intake_readiness",
    ]


def test_repeating_a_published_release_is_a_no_op():
    db = database(True)
    assert publisher.run(db, RELEASE, apply=True) == 0
    assert "set_symptom_question_eligibility" not in names(db)


def test_apply_fails_when_the_database_does_not_confirm():
    assert publisher.run(database(False, False), RELEASE, apply=True) == 1


def test_the_active_release_is_the_one_the_service_loads():
    release = publisher.active_release()
    assert release["version"] == "v2"
    assert all(release["approval"].values())
