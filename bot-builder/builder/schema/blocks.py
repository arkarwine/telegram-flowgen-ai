from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatScope(str, Enum):
    private = "private"
    group = "group"
    supergroup = "supergroup"
    channel = "channel"
    all = "all"


class MatchMode(str, Enum):
    always = "always"
    exact = "exact"
    contains = "contains"
    regex = "regex"
    intent = "intent"


class MediaKind(str, Enum):
    photo = "photo"
    video = "video"
    document = "document"
    audio = "audio"
    voice = "voice"
    sticker = "sticker"


class UserValueType(str, Enum):
    text = "text"
    integer = "integer"
    number = "number"
    boolean = "boolean"
    date = "date"


class DiceEmoji(str, Enum):
    dice = "\U0001F3B2"
    darts = "\U0001F3AF"
    basketball = "\U0001F3C0"
    football = "\u26BD"
    bowling = "\U0001F3B3"
    slot_machine = "\U0001F3B0"


class CurrencyPrice(StrictModel):
    label: str = Field(min_length=1, max_length=64)
    amount_minor_units: int = Field(ge=1)


class ConversationStep(StrictModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    prompt: str = Field(min_length=1, max_length=1024)
    data_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    validation_regex: str | None = Field(default=None, max_length=512)
    retry_message: str = Field(default="Please send that in the expected format.", max_length=512)

    @field_validator("validation_regex")
    @classmethod
    def regex_compiles(cls, value: str | None) -> str | None:
        if value:
            re.compile(value)
        return value


class InlineResult(StrictModel):
    result_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=256)
    message_text: str = Field(min_length=1, max_length=4096)


class UserField(StrictModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    value_type: UserValueType
    prompt: str = Field(default="", max_length=512)
    default_value: str = Field(default="", max_length=512)


class AdminCommand(StrictModel):
    name: str = Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    response: str = Field(min_length=1, max_length=4096)


class PayloadAction(StrictModel):
    pattern: str = Field(min_length=1, max_length=128)
    response: str = Field(min_length=1, max_length=4096)
    store_key: str | None = Field(default=None, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")

    @field_validator("pattern")
    @classmethod
    def payload_regex_compiles(cls, value: str) -> str:
        re.compile(value)
        return value


class BaseBlock(StrictModel):
    id: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    enabled: bool = True
    description: str = Field(default="", max_length=512)


class CommandHandlerBlock(BaseBlock):
    type: Literal["command_handler"] = "command_handler"
    command: str = Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    aliases: list[str] = Field(default_factory=list, max_length=10)
    response: str = Field(min_length=1, max_length=4096)
    scope: ChatScope = ChatScope.all
    persist_user: bool = True

    @field_validator("aliases")
    @classmethod
    def aliases_are_commands(cls, value: list[str]) -> list[str]:
        for alias in value:
            if not re.fullmatch(r"^[a-zA-Z0-9_]{1,32}$", alias):
                raise ValueError(f"{alias} is not a valid command alias")
        return value


class TextHandlerBlock(BaseBlock):
    type: Literal["text_handler"] = "text_handler"
    match_mode: MatchMode = MatchMode.contains
    pattern: str = Field(default="", max_length=512)
    response: str = Field(min_length=1, max_length=4096)
    scope: ChatScope = ChatScope.all
    persist_interaction: bool = True

    @field_validator("pattern")
    @classmethod
    def text_pattern_compiles(cls, value: str) -> str:
        if value:
            re.compile(value)
        return value


class ConversationFlowBlock(BaseBlock):
    type: Literal["conversation_flow"] = "conversation_flow"
    entry_triggers: list[str] = Field(min_length=1, max_length=10)
    steps: list[ConversationStep] = Field(min_length=1, max_length=20)
    final_response: str = Field(min_length=1, max_length=4096)
    cancel_words: list[str] = Field(default_factory=lambda: ["cancel", "stop"], max_length=10)
    scope: ChatScope = ChatScope.private


class InlineQueryHandlerBlock(BaseBlock):
    type: Literal["inline_query_handler"] = "inline_query_handler"
    match_mode: MatchMode = MatchMode.contains
    pattern: str = Field(default="", max_length=256)
    results: list[InlineResult] = Field(min_length=1, max_length=50)

    @field_validator("pattern")
    @classmethod
    def inline_pattern_compiles(cls, value: str) -> str:
        if value:
            re.compile(value)
        return value


class CallbackQueryHandlerBlock(BaseBlock):
    type: Literal["callback_query_handler"] = "callback_query_handler"
    callback_data_pattern: str = Field(min_length=1, max_length=128)
    response: str = Field(min_length=1, max_length=4096)
    edit_message: bool = False
    answer_alert: bool = False

    @field_validator("callback_data_pattern")
    @classmethod
    def callback_pattern_compiles(cls, value: str) -> str:
        re.compile(value)
        return value


class MediaHandlerBlock(BaseBlock):
    type: Literal["media_handler"] = "media_handler"
    media_types: list[MediaKind] = Field(min_length=1, max_length=6)
    response: str = Field(min_length=1, max_length=4096)
    save_files: bool = False
    store_metadata: bool = True
    scope: ChatScope = ChatScope.all


class MediaSenderBlock(BaseBlock):
    type: Literal["media_sender"] = "media_sender"
    trigger_text: str = Field(min_length=1, max_length=128)
    media_type: MediaKind
    source: str = Field(min_length=1, max_length=2048)
    caption: str = Field(default="", max_length=1024)
    scope: ChatScope = ChatScope.all


class SchedulerBlock(BaseBlock):
    type: Literal["scheduler"] = "scheduler"
    name: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4096)
    target_chat_id: int | None = None
    interval_seconds: int | None = Field(default=None, ge=60)
    daily_hour_utc: int | None = Field(default=None, ge=0, le=23)
    daily_minute_utc: int | None = Field(default=None, ge=0, le=59)
    run_on_start: bool = False

    @model_validator(mode="after")
    def has_schedule(self) -> SchedulerBlock:
        if self.interval_seconds is None and (self.daily_hour_utc is None or self.daily_minute_utc is None):
            raise ValueError("scheduler needs interval_seconds or daily_hour_utc plus daily_minute_utc")
        return self


class BroadcastBlock(BaseBlock):
    type: Literal["broadcast"] = "broadcast"
    trigger_text: str = Field(default="broadcast", min_length=1, max_length=128)
    message_template: str = Field(min_length=1, max_length=4096)
    admin_ids: list[int] = Field(default_factory=list, max_length=100)


class UserDataStoreBlock(BaseBlock):
    type: Literal["user_data_store"] = "user_data_store"
    fields: list[UserField] = Field(min_length=1, max_length=50)
    expose_profile_command: bool = True
    scope: ChatScope = ChatScope.private


class AdminPanelBlock(BaseBlock):
    type: Literal["admin_panel"] = "admin_panel"
    admin_ids: list[int] = Field(min_length=1, max_length=100)
    commands: list[AdminCommand] = Field(min_length=1, max_length=50)


class RateLimiterBlock(BaseBlock):
    type: Literal["rate_limiter"] = "rate_limiter"
    max_events: int = Field(default=6, ge=1, le=100)
    window_seconds: int = Field(default=30, ge=1, le=3600)
    applies_to: list[str] = Field(default_factory=lambda: ["*"], min_length=1, max_length=100)
    action_message: str = Field(default="Please slow down and try again in a moment.", max_length=512)


class WelcomeHandlerBlock(BaseBlock):
    type: Literal["welcome_handler"] = "welcome_handler"
    message: str = Field(min_length=1, max_length=4096)
    include_rules: bool = False
    rules_text: str = Field(default="", max_length=4096)


class PollCreatorBlock(BaseBlock):
    type: Literal["poll_creator"] = "poll_creator"
    trigger_text: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=300)
    options: list[str] = Field(min_length=2, max_length=10)
    is_anonymous: bool = False
    allows_multiple_answers: bool = False


class QuizCreatorBlock(BaseBlock):
    type: Literal["quiz_creator"] = "quiz_creator"
    trigger_text: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=300)
    options: list[str] = Field(min_length=2, max_length=10)
    correct_option_id: int = Field(ge=0, le=9)
    explanation: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def correct_option_exists(self) -> QuizCreatorBlock:
        if self.correct_option_id >= len(self.options):
            raise ValueError("correct_option_id must point to an option")
        return self


class DiceRollerBlock(BaseBlock):
    type: Literal["dice_roller"] = "dice_roller"
    trigger_text: str = Field(min_length=1, max_length=128)
    emoji: DiceEmoji = DiceEmoji.dice


class ChatMemberHandlerBlock(BaseBlock):
    type: Literal["chat_member_handler"] = "chat_member_handler"
    on_join_message: str = Field(default="", max_length=4096)
    on_leave_message: str = Field(default="", max_length=4096)
    track_members: bool = True


class FileDownloaderBlock(BaseBlock):
    type: Literal["file_downloader"] = "file_downloader"
    media_types: list[MediaKind] = Field(min_length=1, max_length=6)
    directory: str = Field(default="downloads", min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_./-]+$")
    notify_user: bool = True


class DeepLinkHandlerBlock(BaseBlock):
    type: Literal["deeplink_handler"] = "deeplink_handler"
    payload_actions: list[PayloadAction] = Field(min_length=1, max_length=50)
    default_response: str = Field(default="Welcome.", max_length=4096)


class PaymentHandlerBlock(BaseBlock):
    type: Literal["payment_handler"] = "payment_handler"
    trigger_text: str = Field(min_length=1, max_length=128)
    provider_token_env: str = Field(default="PAYMENT_PROVIDER_TOKEN", pattern=r"^[A-Z0-9_]+$")
    title: str = Field(min_length=1, max_length=32)
    description_text: str = Field(min_length=1, max_length=255)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    prices: list[CurrencyPrice] = Field(min_length=1, max_length=10)
    payload: str = Field(min_length=1, max_length=128)
    start_parameter: str = Field(default="checkout", max_length=64)
    successful_payment_message: str = Field(default="Payment received. Thank you!", max_length=4096)


class LocationHandlerBlock(BaseBlock):
    type: Literal["location_handler"] = "location_handler"
    response: str = Field(min_length=1, max_length=4096)
    store_location: bool = True


class ContactHandlerBlock(BaseBlock):
    type: Literal["contact_handler"] = "contact_handler"
    response: str = Field(min_length=1, max_length=4096)
    store_contact: bool = True


class ForwardedMessageHandlerBlock(BaseBlock):
    type: Literal["forwarded_message_handler"] = "forwarded_message_handler"
    response: str = Field(min_length=1, max_length=4096)
    require_original_sender: bool = False


class StickerSetHandlerBlock(BaseBlock):
    type: Literal["sticker_set_handler"] = "sticker_set_handler"
    trigger_text: str = Field(min_length=1, max_length=128)
    sticker_set_name: str = Field(min_length=1, max_length=128)
    response: str = Field(default="Here is the sticker set.", max_length=4096)
    send_first_sticker: bool = True


class GameHandlerBlock(BaseBlock):
    type: Literal["game_handler"] = "game_handler"
    trigger_text: str = Field(min_length=1, max_length=128)
    game_short_name: str = Field(min_length=1, max_length=64)
    fallback_text: str = Field(default="Launching the game.", max_length=512)


class ChannelPostHandlerBlock(BaseBlock):
    type: Literal["channel_post_handler"] = "channel_post_handler"
    match_mode: MatchMode = MatchMode.always
    pattern: str = Field(default="", max_length=512)
    response: str = Field(default="", max_length=4096)
    log_posts: bool = True

    @field_validator("pattern")
    @classmethod
    def channel_pattern_compiles(cls, value: str) -> str:
        if value:
            re.compile(value)
        return value


class ErrorHandlerBlock(BaseBlock):
    type: Literal["error_handler"] = "error_handler"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "ERROR"
    notify_admins: bool = True
    user_message: str = Field(default="Something went wrong. Please try again later.", max_length=512)


CapabilityBlock = Annotated[
    CommandHandlerBlock
    | TextHandlerBlock
    | ConversationFlowBlock
    | InlineQueryHandlerBlock
    | CallbackQueryHandlerBlock
    | MediaHandlerBlock
    | MediaSenderBlock
    | SchedulerBlock
    | BroadcastBlock
    | UserDataStoreBlock
    | AdminPanelBlock
    | RateLimiterBlock
    | WelcomeHandlerBlock
    | PollCreatorBlock
    | QuizCreatorBlock
    | DiceRollerBlock
    | ChatMemberHandlerBlock
    | FileDownloaderBlock
    | DeepLinkHandlerBlock
    | PaymentHandlerBlock
    | LocationHandlerBlock
    | ContactHandlerBlock
    | ForwardedMessageHandlerBlock
    | StickerSetHandlerBlock
    | GameHandlerBlock
    | ChannelPostHandlerBlock
    | ErrorHandlerBlock,
    Field(discriminator="type"),
]


class BotSchema(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    bot_name: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1000)
    default_language: str = Field(default="en", min_length=2, max_length=16)
    admins: list[int] = Field(default_factory=list, max_length=100)
    chat_scopes: list[ChatScope] = Field(default_factory=lambda: [ChatScope.private], min_length=1, max_length=5)
    blocks: list[CapabilityBlock] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def block_ids_are_unique(self) -> BotSchema:
        ids = [block.id for block in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("block ids must be unique")
        return self
