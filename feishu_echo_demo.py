from __future__ import annotations

from src.interface import FeishuConfig, FeishuInterface, InboundMessage


def handle_message(message: InboundMessage, feishu: FeishuInterface) -> None:
    echo_text = (
        f"收到：{message.text}\n"
        f"receive_id(chat_id):{message.chat_id}"
    )

    if message.chat_type == "p2p":
        feishu.send_text(message.chat_id, echo_text, receive_id_type="chat_id")
        return

    feishu.reply_text(message.message_id, echo_text)


def main() -> None:
    config = FeishuConfig.from_env()
    interface = FeishuInterface(config=config, on_message=handle_message)
    interface.start()


if __name__ == "__main__":
    main()
