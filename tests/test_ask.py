import json
from pathlib import Path
from types import SimpleNamespace

import app.ask as ask_module
from app.ask import get_token_usage_summary


def test_get_token_usage_summary_extracts_prompt_and_candidates_tokens():
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=123,
            candidates_token_count=45,
        )
    )

    assert get_token_usage_summary(response) == (123, 45)


def test_ask_keeps_history_across_questions(tmp_path, monkeypatch):
    history_path = tmp_path / "conversation.json"
    history_path.write_text(
        json.dumps([
            {"role": "user", "parts": [{"text": "LoRAとは？"}]},
            {"role": "model", "parts": [{"text": "低ランク適応です"}]},
        ]),
        encoding="utf-8",
    )

    class FakeChat:
        def __init__(self, *, model, history=None):
            self.model = model
            self.history = list(history or [])

        def send_message(self, question):
            self.history.append({"role": "user", "parts": [{"text": question}]})
            reply = SimpleNamespace(
                text=f"続きの回答: {question}",
                usage_metadata=SimpleNamespace(prompt_token_count=9, candidates_token_count=4),
            )
            self.history.append({"role": "model", "parts": [{"text": reply.text}]})
            return reply

    class FakeClient:
        def __init__(self, *, api_key):
            self.api_key = api_key
            self.chats = SimpleNamespace(create=lambda *, model, history=None: FakeChat(model=model, history=history))

    monkeypatch.setattr(ask_module.genai, "Client", FakeClient)

    result = ask_module.ask("例を教えて", history_file=history_path)

    assert result == "続きの回答: 例を教えて"
    saved_history = json.loads(history_path.read_text(encoding="utf-8"))
    assert saved_history[-2]["parts"][0]["text"] == "例を教えて"
    assert saved_history[-1]["parts"][0]["text"] == "続きの回答: 例を教えて"
