from __future__ import annotations

import asyncio
import threading
from collections import deque
from queue import Queue

from src.agents.agent import Agent
from src.agents.types import AgentEvent, AgentResult
from src.interface import FeishuConfig, FeishuInterface, InboundMessage


async def on_event(event: AgentEvent):
    print(event)


agent = Agent(
    provider="codex",
    role="飞书对话助手",
    env={"http_proxy": "http://127.0.0.1:17890",
         "https_proxy": "http://127.0.0.1:17890"}
)

_processed_lock = threading.Lock()
_processed_ids: set[str] = set()
_processed_order: deque[str] = deque()
_processed_limit = 1000


def run_agent_sync(prompt: str) -> AgentResult:
    async def _run() -> AgentResult:
        return await agent.run(prompt, on_event=on_event)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run())

    result_queue: Queue[tuple[AgentResult | None, BaseException | None]] = Queue(maxsize=1)

    def _worker() -> None:
        try:
            result_queue.put((asyncio.run(_run()), None))
        except BaseException as exc:  # pragma: no cover - defensive runtime guard
            result_queue.put((None, exc))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    result, err = result_queue.get()
    if err is not None:
        raise err
    assert result is not None
    return result


def should_ignore_message(message: InboundMessage) -> bool:
    # Ignore bot/app self messages to prevent reply loops.
    sender = getattr(getattr(message.raw, "event", None), "sender", None)
    sender_type = getattr(sender, "sender_type", "")
    if sender_type == "app":
        return True

    # Feishu may retry event delivery; dedupe by message_id.
    with _processed_lock:
        if message.message_id in _processed_ids:
            return True
        _processed_ids.add(message.message_id)
        _processed_order.append(message.message_id)
        if len(_processed_order) > _processed_limit:
            expired = _processed_order.popleft()
            _processed_ids.discard(expired)
    return False


def handle_message(message: InboundMessage, feishu: FeishuInterface) -> None:
    if should_ignore_message(message):
        return

    if message.message_type != "text":
        reply_text = f"仅支持文本消息。\n"
    else:
        result = run_agent_sync(message.text)
        if result.status == "success":
            reply_text = result.message or str(result.data) or "处理成功，但无返回内容。"
        else:
            reply_text = f"处理失败：{result.error or result.message or '未知错误'}"
        reply_text = f"{reply_text}\n"

    if message.chat_type == "p2p":
        feishu.send_text(message.chat_id, reply_text, receive_id_type="chat_id")
        return
    feishu.reply_text(message.message_id, reply_text)


def main() -> None:
    feishu_cfg = FeishuConfig.from_env()
    interface = FeishuInterface(config=feishu_cfg, on_message=handle_message)
    interface.start()


if __name__ == "__main__":
    main()
