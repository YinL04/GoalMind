from __future__ import annotations

import json
from datetime import datetime

from app.agent import answer_football_question, check_llm_connection, get_llm_status


def main() -> None:
    print("足球球迷问答 Agent")
    print("自由输入问题，输入 exit / quit / 退出 结束。")
    print()
    _print_llm_status()
    _maybe_check_connection()

    while True:
        try:
            question = input("\n你想问：").strip()
        except EOFError:
            print("\n输入已结束，退出。")
            break
        if question.lower() in {"exit", "quit"} or question == "退出":
            print("已退出。")
            break
        if not question:
            continue

        try:
            print()
            answer = answer_football_question(question, progress=_print_progress)
        except Exception as exc:
            print(f"生成失败：{exc}")
            continue

        print("\n=== 回答 ===")
        print(json.dumps(answer.model_dump(), ensure_ascii=False, indent=2))

def _print_llm_status() -> None:
    status = get_llm_status()
    print("=== LLM 配置 ===")
    print(f"状态：{'已读取 API key' if status['configured'] else '未读取到 API key'}")
    print(f"Key：{status['api_key_preview']}")
    print(f"模型：{status['model']}")
    print(f"Base URL：{status['base_url']}")


def _maybe_check_connection() -> None:
    try:
        choice = input("\n是否现在测试一次 LLM 连接？这会发起一次很短的模型调用。[Y/n] ").strip().lower()
    except EOFError:
        print("\n未检测到交互输入，已跳过连接测试。")
        return
    if choice in {"n", "no"}:
        print("已跳过连接测试。")
        return

    print("正在测试 LLM 连接...")
    result = check_llm_connection()
    if result["ok"]:
        print(f"LLM 连接：成功。模型响应：{result.get('response', '')}")
    else:
        print(f"LLM 连接：失败。原因：{result.get('error', '未知错误')}")


def _print_progress(message: str) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {message}", flush=True)


if __name__ == "__main__":
    main()
