"""第1回: 素のLLMに1回だけ質問するスクリプト。

使い方:
    uv run python -m app.ask "LoRAとは何ですか？"
    uv run python -m app.ask            # 質問を省略すると、講座に固有の質問をする

ツールも会話履歴も持たない「素の」呼び出し。
講座に固有のことを聞くと、「分からない」と答えるか、一般論でもっともらしく答える
（講座の実際とは違う）ことを確かめよう。
（第3回で、用語集を検索できるエージェントにして改善する）
"""

import argparse
import json
from pathlib import Path

from google import genai
from google.genai import errors

from app.config import MODEL, api_error_message, get_api_key

# 講座に固有の質問。正しい答えは data/glossary.json の homework-levels にある
DEFAULT_QUESTION = "AIE2026の講座の宿題にある「3レベル」とは何ですか？"
DEFAULT_HISTORY_FILE = Path(".conversation_history.json")


def get_token_usage_summary(response) -> tuple[int, int]:
    """生成レスポンスから入力トークン数と出力トークン数を取り出す。"""
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return 0, 0

    prompt_tokens = getattr(metadata, "prompt_token_count", None)
    candidate_tokens = getattr(metadata, "candidates_token_count", None)

    return (
        int(prompt_tokens) if prompt_tokens is not None else 0,
        int(candidate_tokens) if candidate_tokens is not None else 0,
    )


def _load_history(history_file: Path | str | None) -> list[dict]:
    path = Path(history_file) if history_file is not None else DEFAULT_HISTORY_FILE
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    return data if isinstance(data, list) else []


def _normalize_history(history) -> list[dict]:
    normalized: list[dict] = []
    for item in history or []:
        if isinstance(item, dict):
            normalized.append(item)
            continue

        role = getattr(item, "role", "user")
        parts: list[dict] = []
        for part in getattr(item, "parts", []) or []:
            if isinstance(part, dict):
                parts.append(part)
            elif hasattr(part, "text"):
                parts.append({"text": part.text})
            elif isinstance(part, str):
                parts.append({"text": part})
            else:
                parts.append({"text": str(part)})

        normalized.append({"role": role, "parts": parts})

    return normalized


def _save_history(history, history_file: Path | str | None) -> None:
    path = Path(history_file) if history_file is not None else DEFAULT_HISTORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_normalize_history(history), ensure_ascii=False, indent=2), encoding="utf-8")


def ask(question: str, history_file: Path | str | None = None) -> str:
    history_path = Path(history_file) if history_file is not None else DEFAULT_HISTORY_FILE
    client = genai.Client(api_key=get_api_key())

    history = _load_history(history_path)
    chat = client.chats.create(model=MODEL, history=history)
    response = chat.send_message(question)

    current_history = getattr(chat, "get_history", lambda: getattr(chat, "history", history))()
    _save_history(current_history, history_path)

    input_tokens, output_tokens = get_token_usage_summary(response)
    print(f"[入力トークン数] {input_tokens}")
    print(f"[出力トークン数] {output_tokens}")

    return response.text


def main() -> None:
    parser = argparse.ArgumentParser(description="素のLLMに質問する")
    parser.add_argument("question", nargs="?", default=None)
    parser.add_argument(
        "--history-file",
        type=str,
        default=str(DEFAULT_HISTORY_FILE),
        help="会話履歴を保存するファイル",
    )
    args = parser.parse_args()

    print(f"[model] {MODEL}")

    if args.question is None:
        print("[会話モード]")
        print("終了: exit / 会話のリセット: /reset\n")

        while True:
            try:
                question = input("Q> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n終了します。")
                break

            # 空入力なら、もう一度入力を待つ
            if not question:
                continue

            # 終了する
            if question.lower() in {"quit", "exit", "q"}:
                break

            # 保存された履歴を削除して、新しい会話にする
            if question.lower() == "/reset":
                try:
                    Path(args.history_file).unlink(missing_ok=True)
                    print("会話履歴をリセットしました。\n")
                except OSError as e:
                    print(f"履歴をリセットできませんでした: {e}\n")
                continue

            # APIエラーが起きても、プログラムを終了させない
            try:
                answer = ask(question, history_file=args.history_file)
                print(f"AI> {answer}\n")
            except errors.APIError as e:
                print(api_error_message(e.code, e.message))

        return

    print(f"[質問] {args.question}\n")
    try:
        print(ask(args.question, history_file=args.history_file))
    except errors.APIError as e:
        print(api_error_message(e.code, e.message))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
