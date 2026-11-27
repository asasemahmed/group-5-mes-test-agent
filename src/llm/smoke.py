"""Smoke test for the model: does it work for our agent before we build on it?

Usage:  python -m src.llm.smoke              (model info + both paid probes, needs OPENROUTER_API_KEY)
        python -m src.llm.smoke --info-only  (model info only, free, no key)

1. Model info (free): looks the model up in OpenRouter's public model list and prints
   its input types, prices and whether it accepts a JSON response format.
2. Two probes (paid, a fraction of a cent): both show the model a small page and ask
   for one action as JSON.
   - image probe: a screenshot plus the element list. The screenshot also shows a
     code word that appears nowhere in the text, and the answer must repeat it,
     which proves the image was read.
   - text probe: the element list and page text only, no image.

The result decides the observation mode (design 14, plan 0.2) and is saved to
reports/smoke/. The API key is sent only to https://openrouter.ai and never printed.
"""

import argparse
import base64
import json
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import httpx

from src.config import ROOT, load_settings

OPENROUTER_ORIGIN = "https://openrouter.ai"
CHAT_URL = OPENROUTER_ORIGIN + "/api/v1/chat/completions"
MODELS_URL = OPENROUTER_ORIGIN + "/api/v1/models"

CODE_WORDS = ["MAGNOLIA", "TURBINE", "PELICAN", "COBALT", "HARBOUR", "VIOLET"]

PAGE_TEXT = "Spare parts\nSearch parts [ ] Search\nIssue spare part"
ELEMENTS = '[1] textbox "Search parts" value=""\n[2] button "Search"\n[3] link "Issue spare part"'
TASK = "Open the form to issue a spare part."
EXPECTED = {"action": "click", "element": 3}

SYSTEM_PROMPT = (
    "You operate a web page for a tester. You get a task, the visible text of the page and a "
    "numbered list of its interactive elements. Choose exactly one next action. Answer with one "
    'JSON object and nothing else, for example {"action": "click", "element": 2}.'
)


def page_html(word: str) -> str:
    """The probe page. The code word is drawn in the image only."""
    return f"""<!doctype html><html><body style="font-family: Arial; margin: 32px; width: 600px">
<h1>Spare parts</h1>
<label>Search parts <input type="text"></label> <button>Search</button>
<p><a href="#">Issue spare part</a></p>
<div style="margin-top: 32px; padding: 16px; background: #ffe45c; font-size: 40px; font-weight: bold">{word}</div>
</body></html>"""


def render_probe_image(word: str) -> bytes:
    """Screenshot of the probe page as JPEG, made with the same Chromium the agent uses."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 700, "height": 360})
            page.set_content(page_html(word))
            return page.screenshot(type="jpeg", quality=80)
        finally:
            browser.close()


@dataclass
class ProbeResult:
    name: str
    passed: bool = False
    http_status: int | None = None
    latency_s: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    json_format_accepted: bool | None = None
    reply: str = ""
    problem: str = ""
    details: dict = field(default_factory=dict)


def model_info(client: httpx.Client, model_id: str) -> dict | None:
    """The model's entry in OpenRouter's public list, or None if it is not there."""
    response = client.get(MODELS_URL)
    response.raise_for_status()
    for model in response.json().get("data", []):
        if model.get("id") == model_id:
            arch = model.get("architecture") or {}
            pricing = model.get("pricing") or {}
            per_mtok = lambda v: round(float(v) * 1_000_000, 6) if v not in (None, "") else None
            return {
                "id": model_id,
                "input_modalities": arch.get("input_modalities") or [],
                "price_input_per_mtok": per_mtok(pricing.get("prompt")),
                "price_output_per_mtok": per_mtok(pricing.get("completion")),
                "supports_response_format": "response_format" in (model.get("supported_parameters") or []),
                "context_length": model.get("context_length"),
            }
    return None


def _post(client: httpx.Client, api_key: str, body: dict) -> httpx.Response:
    return client.post(CHAT_URL, headers={"Authorization": f"Bearer {api_key}"}, json=body, timeout=60)


def run_probe(client: httpx.Client, api_key: str, model_id: str, name: str, image_jpeg: bytes | None, word: str | None) -> ProbeResult:
    result = ProbeResult(name=name)
    user_text = f"Task: {TASK}\n\nPage text:\n{PAGE_TEXT}\n\nElements:\n{ELEMENTS}"
    if image_jpeg is not None:
        user_text += (
            '\n\nThe screenshot also shows a code word in a yellow box. Add it to your answer as "word", '
            'for example {"action": "click", "element": 2, "word": "EXAMPLE"}.'
        )
        content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode()}},
        ]
    else:
        content = user_text

    body = {
        "model": model_id,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
        "usage": {"include": True},
    }

    start = time.monotonic()
    response = _post(client, api_key, body)
    result.json_format_accepted = True
    if response.status_code == 400 and "response_format" in response.text:
        # Accepted by the model list but refused here: try once more without it.
        result.json_format_accepted = False
        body.pop("response_format")
        response = _post(client, api_key, body)
    result.latency_s = round(time.monotonic() - start, 2)
    result.http_status = response.status_code

    if response.status_code != 200:
        result.problem = f"HTTP {response.status_code}: {response.text[:300]}"
        return result

    data = response.json()
    usage = data.get("usage") or {}
    result.prompt_tokens = usage.get("prompt_tokens")
    result.completion_tokens = usage.get("completion_tokens")
    result.cost_usd = usage.get("cost")
    choices = data.get("choices") or []
    result.reply = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""

    try:
        answer = parse_json_object(result.reply)
    except ValueError as error:
        result.problem = f"reply is not a JSON object: {error}"
        return result

    result.details = {"answer": answer}
    action_ok = str(answer.get("action", "")).lower() == EXPECTED["action"] and _as_int(answer.get("element")) == EXPECTED["element"]
    word_ok = word is None or str(answer.get("word", "")).strip().upper() == word
    result.passed = action_ok and word_ok
    if not action_ok:
        result.problem = f"wrong action, expected {EXPECTED}"
    elif not word_ok:
        result.problem = f"code word not read correctly (expected {word})"
    return result


def parse_json_object(text: str) -> dict:
    """Parse a JSON object, tolerating a ```json fence around it."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError(str(error)) from None
    if not isinstance(value, dict):
        raise ValueError("not an object")
    return value


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def decide_mode(image_passed: bool, text_passed: bool) -> str | None:
    """Observation mode for the experiment, or None if the live experiment is blocked."""
    if image_passed:
        return "image"
    if text_passed:
        return "text"
    return None


def main(argv: list[str] | None = None, transport: httpx.BaseTransport | None = None, renderer=render_probe_image) -> int:
    parser = argparse.ArgumentParser(description="Check that the model works for the agent.")
    parser.add_argument("--info-only", action="store_true", help="only look up the model, no paid request")
    args = parser.parse_args(argv)

    settings = load_settings()
    report = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": settings.llm_model}

    with httpx.Client(transport=transport) as client:
        info = model_info(client, settings.llm_model)
        report["model_info"] = info
        if info is None:
            print(f"Model {settings.llm_model!r} is not in OpenRouter's model list. The live experiment is blocked.")
            _save(report)
            return 2
        print(f"Model: {info['id']}")
        print(f"  input types:        {', '.join(info['input_modalities'])}")
        print(f"  price per 1M tokens: input ${info['price_input_per_mtok']}, output ${info['price_output_per_mtok']}")
        print(f"  JSON response format listed: {info['supports_response_format']}")
        if args.info_only:
            _save(report)
            return 0

        if not settings.openrouter_api_key:
            print("\nNo OPENROUTER_API_KEY in .env or the environment, so the paid probes were not run.")
            _save(report)
            return 1

        word = random.choice(CODE_WORDS)
        image_probe = run_probe(client, settings.openrouter_api_key, settings.llm_model, "image", renderer(word), word)
        text_probe = run_probe(client, settings.openrouter_api_key, settings.llm_model, "text", None, None)

    report["probes"] = [asdict(image_probe), asdict(text_probe)]
    mode = decide_mode(image_probe.passed, text_probe.passed)
    report["observation_mode"] = mode

    for probe in (image_probe, text_probe):
        status = "PASS" if probe.passed else "FAIL"
        cost = "not returned" if probe.cost_usd is None else f"${probe.cost_usd}"
        print(f"\n{probe.name} probe: {status}")
        print(f"  HTTP {probe.http_status}, {probe.latency_s} s, tokens in/out {probe.prompt_tokens}/{probe.completion_tokens}, cost {cost}")
        print(f"  JSON response format accepted: {probe.json_format_accepted}")
        print(f"  reply: {probe.reply[:200]}")
        if probe.problem:
            print(f"  problem: {probe.problem}")

    path = _save(report)
    if mode is None:
        print("\nNeither probe passed. The live experiment is blocked; the team decides how to continue.")
        print(f"Saved to {path}")
        return 2
    print(f"\nObservation mode for the experiment: {mode}")
    print(f"Saved to {path}")
    return 0


def _save(report: dict):
    folder = ROOT / "reports" / "smoke"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"smoke-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    sys.exit(main())
