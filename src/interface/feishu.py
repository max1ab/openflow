from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

import lark_oapi as lark
from dotenv import load_dotenv
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)


@dataclass(slots=True)
class FeishuConfig:
    app_id: str
    app_secret: str
    verification_token: str = ""
    encrypt_key: str = ""
    log_level: int = lark.LogLevel.INFO

    @classmethod
    def from_env(cls) -> "FeishuConfig":
        load_dotenv()
        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        verification_token = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
        encrypt_key = os.getenv("FEISHU_ENCRYPT_KEY", "")
        return cls(
            app_id=app_id,
            app_secret=app_secret,
            verification_token=verification_token,
            encrypt_key=encrypt_key,
        )


@dataclass(slots=True)
class InboundMessage:
    message_id: str
    chat_id: str
    chat_type: str
    message_type: str
    sender_id: str
    text: str
    raw: Any


MessageCallback = Callable[[InboundMessage, "FeishuInterface"], None]


class FeishuInterface:
    def __init__(self, config: FeishuConfig, on_message: Optional[MessageCallback] = None) -> None:
        if not config.app_id or not config.app_secret:
            raise ValueError("Missing Feishu credentials: FEISHU_APP_ID / FEISHU_APP_SECRET")

        self._config = config
        self._on_message = on_message
        self._client = lark.Client.builder().app_id(config.app_id).app_secret(config.app_secret).build()
        self._event_handler = (
            lark.EventDispatcherHandler.builder(config.verification_token, config.encrypt_key)
            .register_p2_im_message_receive_v1(self._on_message_event)
            .build()
        )
        self._ws_client = lark.ws.Client(
            config.app_id,
            config.app_secret,
            event_handler=self._event_handler,
            log_level=config.log_level,
        )

    def _on_message_event(self, data: P2ImMessageReceiveV1) -> None:
        inbound = self._parse_inbound_message(data)
        if self._on_message is not None:
            self._on_message(inbound, self)

    def _parse_inbound_message(self, data: P2ImMessageReceiveV1) -> InboundMessage:
        event_message = data.event.message
        sender = getattr(data.event, "sender", None)
        sender_id = ""
        if sender and getattr(sender, "sender_id", None):
            sender_id = (
                getattr(sender.sender_id, "open_id", "")
                or getattr(sender.sender_id, "user_id", "")
                or getattr(sender.sender_id, "union_id", "")
            )

        text = self._extract_text(event_message.message_type, event_message.content)
        return InboundMessage(
            message_id=event_message.message_id,
            chat_id=event_message.chat_id,
            chat_type=event_message.chat_type,
            message_type=event_message.message_type,
            sender_id=sender_id,
            text=text,
            raw=data,
        )

    @staticmethod
    def _extract_text(message_type: str, content: str) -> str:
        if message_type != "text":
            return "解析消息失败，请发送文本消息"

        try:
            content_obj = json.loads(content)
        except json.JSONDecodeError:
            return "解析消息失败，请发送文本消息"
        return str(content_obj.get("text", ""))

    def send_text(self, receive_id: str, text: str, receive_id_type: str = "chat_id") -> None:
        content = json.dumps({"text": text}, ensure_ascii=False)
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError(
                "client.im.v1.message.create failed, "
                f"code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}"
            )

    def reply_text(self, message_id: str, text: str) -> None:
        content = json.dumps({"text": text}, ensure_ascii=False)
        request = (
            ReplyMessageRequest.builder()
            .message_id(message_id)
            .request_body(ReplyMessageRequestBody.builder().content(content).msg_type("text").build())
            .build()
        )
        response = self._client.im.v1.message.reply(request)
        if not response.success():
            raise RuntimeError(
                "client.im.v1.message.reply failed, "
                f"code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}"
            )

    def start(self) -> None:
        self._ws_client.start()
