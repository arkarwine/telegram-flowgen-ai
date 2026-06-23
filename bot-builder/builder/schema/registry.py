from __future__ import annotations

from pydantic import BaseModel

from builder.schema.blocks import (
    AdminPanelBlock,
    BroadcastBlock,
    CallbackQueryHandlerBlock,
    ChannelPostHandlerBlock,
    ChatMemberHandlerBlock,
    CommandHandlerBlock,
    ContactHandlerBlock,
    ConversationFlowBlock,
    DeepLinkHandlerBlock,
    DiceRollerBlock,
    ErrorHandlerBlock,
    FileDownloaderBlock,
    ForwardedMessageHandlerBlock,
    GameHandlerBlock,
    InlineQueryHandlerBlock,
    LocationHandlerBlock,
    MediaHandlerBlock,
    MediaSenderBlock,
    PaymentHandlerBlock,
    PollCreatorBlock,
    QuizCreatorBlock,
    RateLimiterBlock,
    SchedulerBlock,
    StickerSetHandlerBlock,
    TextHandlerBlock,
    UserDataStoreBlock,
    WelcomeHandlerBlock,
)


BLOCK_MODELS: dict[str, type[BaseModel]] = {
    "text_handler": TextHandlerBlock,
    "command_handler": CommandHandlerBlock,
    "conversation_flow": ConversationFlowBlock,
    "inline_query_handler": InlineQueryHandlerBlock,
    "callback_query_handler": CallbackQueryHandlerBlock,
    "media_handler": MediaHandlerBlock,
    "media_sender": MediaSenderBlock,
    "scheduler": SchedulerBlock,
    "broadcast": BroadcastBlock,
    "user_data_store": UserDataStoreBlock,
    "admin_panel": AdminPanelBlock,
    "rate_limiter": RateLimiterBlock,
    "welcome_handler": WelcomeHandlerBlock,
    "poll_creator": PollCreatorBlock,
    "quiz_creator": QuizCreatorBlock,
    "dice_roller": DiceRollerBlock,
    "chat_member_handler": ChatMemberHandlerBlock,
    "file_downloader": FileDownloaderBlock,
    "deeplink_handler": DeepLinkHandlerBlock,
    "payment_handler": PaymentHandlerBlock,
    "location_handler": LocationHandlerBlock,
    "contact_handler": ContactHandlerBlock,
    "forwarded_message_handler": ForwardedMessageHandlerBlock,
    "sticker_set_handler": StickerSetHandlerBlock,
    "game_handler": GameHandlerBlock,
    "channel_post_handler": ChannelPostHandlerBlock,
    "error_handler": ErrorHandlerBlock,
}


def block_type_names() -> list[str]:
    return sorted(BLOCK_MODELS)


def registry_prompt() -> str:
    lines = [
        "Allowed capability block types and their Pydantic JSON schemas:",
    ]
    for block_type, model in sorted(BLOCK_MODELS.items()):
        lines.append(f"\n{block_type}:")
        lines.append(model.model_json_schema(mode="validation").__repr__())
    return "\n".join(lines)

