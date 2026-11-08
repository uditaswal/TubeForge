from tubeforge.pipeline.script_fit import analyze_script, plan_template, script_guide, spoken_words
from tubeforge.batch_plans import parse_batch
from tubeforge.rendering.shorts.spoken import prepare_spoken


def test_fit_reports_over_and_under_length():
    long_text = "\n\n".join(["One two three four five six seven eight nine ten."] * 22)
    over = analyze_script(long_text, 60)
    assert over["status"] == "too_long" and "Remove about" in over["suggestion"]
    under = analyze_script("Short line here for you today friends ok.", 60)
    assert under["status"] == "too_short" and "Add about" in under["suggestion"]
    ok = analyze_script(["One two three four five six seven eight nine ten."] * 15, 60)
    assert ok["status"] == "ok" and ok["section_count"] == 15


def test_tags_are_not_words_and_sections_are_flagged():
    assert spoken_words("A [pause 0.4] *real* [breath] thing") == 3
    rows = analyze_script("Tiny.\n\n" + "word " * 20, 60)["sections"]
    assert "too short" in rows[0]["note"] and "too long" in rows[1]["note"]


def test_single_paragraph_splits_into_sentences():
    assert analyze_script("First sentence here. Second one there! Third?", 30)["section_count"] == 3


def test_template_parses_as_a_batch_plan_for_every_length():
    for length in (30, 45, 60, 75, 90):
        plan = parse_batch(plan_template(length).replace("my-short-id", "x1"))
        assert not plan.errors, plan.errors
        assert plan.shorts[0].length_s == length and plan.shorts[0].narration
        assert str(length) in script_guide(length)


def test_readme_is_read_as_a_word_but_real_acronyms_are_spelled():
    spoken = prepare_spoken("Its README lists API, HTTPS and JSON.", profile="spoken-v1", lexicon={}).text
    assert "read me" in spoken and "jason" in spoken
    assert "eh pee eye" in spoken and "aitch tee tee pee ess" in spoken


def test_script_fit_and_guide_endpoints_and_dashboard_controls(tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from tests.test_api_workflow import _migrate
    from tubeforge.api.app import create_app
    from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
    db = tmp_path / "s.db"
    _migrate(db)
    settings = Settings(app=AppConfig(name="t", environment="test"), database=DatabaseConfig(url=f"sqlite:///{db}"), auth=AuthConfig(enabled=True))
    with TestClient(create_app(settings)) as client:
        client.app.state.runtime.auth.create_admin("script-op", "correct-horse-battery-staple")
        assert client.post("/login", json={"username": "script-op", "password": "correct-horse-battery-staple"}).status_code == 200
        client.headers["x-csrf-token"] = client.cookies["tubeforge_csrf"]
        fit = client.post("/api/script-fit", json={"text": "Hello there friends and neighbours today.", "length_s": 60}).json()
        assert fit["status"] == "too_short" and fit["max_words"] == 177
        assert client.post("/api/script-fit", json={"length_s": 60}).status_code == 422
        guide = client.get("/api/script-guide?length_s=45").json()["markdown"]
        assert "45-second" in guide and "narration: |" in guide
        assert "narration: |" in client.get("/api/script-guide?kind=format&length_s=30").json()["markdown"]
        assert client.get("/api/script-guide?length_s=200").status_code == 422
        page = client.get("/").text
        assert "operatorScript" in page and "Copy AI script guide" in page
        plan = "## A\n\n```yaml\nid: a-1\ntitle: T\nconcept: C\nbeats:\n  - {t: 0, point: Hook}\nnarration: |\n  One two three four five six seven eight nine ten.\n```\n"
        data = client.post("/api/batch-plans/import", json={"markdown": plan}).json()
        assert data["script_fit"]["a-1"]["status"] == "too_short"
