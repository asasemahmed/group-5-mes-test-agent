"""Offline tests for the model smoke test: a fake OpenRouter answers, nothing is paid."""

import json

import httpx
import pytest

from src.config import Settings
from src.llm import smoke

KEY = "sk-or-v1-canary-1234567890"
MODEL = "z-ai/glm-5.3-flash"

MODEL_LIST = {
    "data": [
        {
            "id": MODEL,
            "architecture": {"input_modalities": ["text", "image", "video"]},
            "pricing": {"prompt": "0.00000015", "completion": "0.0000005"},
            "supported_parameters": ["max_tokens", "response_format", "temperature"],
            "context_length": 1048576,
        }
    ]
}


def chat_reply(content: str) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 12, "cost": 0.00002},
    }


class FakeOpenRouter:
    """Answers like OpenRouter. image_reply / text_reply return the reply text for a probe."""

    def __init__(self, image_reply, text_reply, models=MODEL_LIST, refuse_response_format=False):
        self.image_reply = image_reply
        self.text_reply = text_reply
        self.models = models
        self.refuse_response_format = refuse_response_format
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.scheme == "https" and request.url.host == "openrouter.ai"
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json=self.models)
        assert request.url.path == "/api/v1/chat/completions"
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        body = json.loads(request.content)
        if self.refuse_response_format and "response_format" in body:
            return httpx.Response(400, text='{"error": "response_format is not supported"}')
        content = body["messages"][1]["content"]
        has_image = isinstance(content, list) and any(part["type"] == "image_url" for part in content)
        reply = self.image_reply if has_image else self.text_reply
        return httpx.Response(200, json=chat_reply(reply(body)))


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr(smoke, "load_settings", lambda: Settings(openrouter_api_key=KEY, llm_model=MODEL))
    monkeypatch.setattr(smoke.random, "choice", lambda words: "PELICAN")
    return tmp_path


def fake_renderer(word):
    return b"\xff\xd8fake-jpeg-" + word.encode()


def run(fake, argv=None):
    return smoke.main(argv or [], transport=httpx.MockTransport(fake), renderer=fake_renderer)


def saved_report(root):
    files = list((root / "reports" / "smoke").glob("smoke-*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text())


GOOD_IMAGE = lambda body: '{"action": "click", "element": 3, "word": "pelican"}'
GOOD_TEXT = lambda body: '{"action": "click", "element": 3}'
WRONG_WORD = lambda body: '{"action": "click", "element": 3, "word": "PENGUIN"}'
WRONG_ACTION = lambda body: '{"action": "type", "element": 1, "text": "issue"}'
NOT_JSON = lambda body: "I would click the link."


@pytest.mark.parametrize(
    "image_reply, text_reply, exit_code, mode",
    [
        (GOOD_IMAGE, GOOD_TEXT, 0, "image"),
        (GOOD_IMAGE, WRONG_ACTION, 0, "image"),
        (WRONG_WORD, GOOD_TEXT, 0, "text"),
        (NOT_JSON, WRONG_ACTION, 2, None),
    ],
)
def test_four_outcomes_decide_the_mode(setup, capsys, image_reply, text_reply, exit_code, mode):
    fake = FakeOpenRouter(image_reply, text_reply)
    assert run(fake) == exit_code
    report = saved_report(setup)
    assert report["observation_mode"] == mode
    assert [p["name"] for p in report["probes"]] == ["image", "text"]


def test_image_is_sent_only_in_the_image_probe_and_word_only_in_the_image(setup):
    fake = FakeOpenRouter(GOOD_IMAGE, GOOD_TEXT)
    run(fake)
    chats = [json.loads(r.content) for r in fake.requests if r.url.path.endswith("/chat/completions")]
    image_content, text_content = chats[0]["messages"][1]["content"], chats[1]["messages"][1]["content"]
    assert image_content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert isinstance(text_content, str)
    for body in chats:
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        texts = [system] + ([user] if isinstance(user, str) else [p["text"] for p in user if p["type"] == "text"])
        assert all("PELICAN" not in t for t in texts)
        assert body["model"] == MODEL and body["max_tokens"] and body["temperature"] == 0


def test_cost_tokens_and_fenced_json_are_read(setup):
    fake = FakeOpenRouter(lambda b: '```json\n{"action": "click", "element": "3", "word": "PELICAN"}\n```', GOOD_TEXT)
    assert run(fake) == 0
    image = saved_report(setup)["probes"][0]
    assert image["passed"] is True
    assert (image["prompt_tokens"], image["completion_tokens"], image["cost_usd"]) == (120, 12, 0.00002)


def test_refused_response_format_is_retried_without_it(setup):
    fake = FakeOpenRouter(GOOD_IMAGE, GOOD_TEXT, refuse_response_format=True)
    assert run(fake) == 0
    probes = saved_report(setup)["probes"]
    assert all(p["json_format_accepted"] is False and p["passed"] for p in probes)


def test_missing_model_blocks_without_a_paid_request(setup):
    fake = FakeOpenRouter(GOOD_IMAGE, GOOD_TEXT, models={"data": []})
    assert run(fake) == 2
    assert all(r.url.path == "/api/v1/models" for r in fake.requests)


def test_no_key_runs_no_paid_request(setup, monkeypatch):
    monkeypatch.setattr(smoke, "load_settings", lambda: Settings(openrouter_api_key=None, llm_model=MODEL))
    fake = FakeOpenRouter(GOOD_IMAGE, GOOD_TEXT)
    assert run(fake) == 1
    assert all(r.url.path == "/api/v1/models" for r in fake.requests)


def test_info_only_is_free_and_reports_prices(setup, capsys):
    fake = FakeOpenRouter(GOOD_IMAGE, GOOD_TEXT)
    assert run(fake, ["--info-only"]) == 0
    assert all(r.url.path == "/api/v1/models" for r in fake.requests)
    info = saved_report(setup)["model_info"]
    assert (info["price_input_per_mtok"], info["price_output_per_mtok"]) == (0.15, 0.5)
    assert "image" in info["input_modalities"]


def test_key_is_never_printed_or_saved(setup, capsys):
    fake = FakeOpenRouter(GOOD_IMAGE, lambda b: '{"error": "bad"}')
    run(fake)
    out = capsys.readouterr()
    assert KEY not in out.out and KEY not in out.err
    assert KEY not in (setup / "reports" / "smoke").glob("*.json").__next__().read_text()


def test_probe_image_is_a_jpeg_rendered_by_chromium():
    image = smoke.render_probe_image("PELICAN")
    assert image[:2] == b"\xff\xd8" and len(image) > 2000
