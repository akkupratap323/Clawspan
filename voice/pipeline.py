"""JARVIS voice pipeline orchestrator.

Flow:
  Mic → Silero VAD → Deepgram STT → JarvisProcessor → Cartesia TTS → Speaker

JarvisProcessor runs a single streaming LLM turn per user utterance,
pushes sentences to TTS as they arrive, and fires tools in background
threads so the voice never has to wait on I/O.

Public entry point: `run_pipeline()`.
"""

from __future__ import annotations

import asyncio
import json
import random
import re

from loguru import logger
from openai import AsyncOpenAI

from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMContextFrame, TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.cartesia.tts import CartesiaTTSService, CartesiaTTSSettings
from pipecat.services.deepgram.stt import DeepgramSTTService, DeepgramSTTSettings
from pipecat.services.tts_service import TextAggregationMode
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.turns.user_mute.mute_until_first_bot_complete_user_mute_strategy import (
    MuteUntilFirstBotCompleteUserMuteStrategy,
)
from pipecat.turns.user_start.min_words_user_turn_start_strategy import MinWordsUserTurnStartStrategy
from pipecat.turns.user_start.vad_user_turn_start_strategy import VADUserTurnStartStrategy
from pipecat.turns.user_stop.speech_timeout_user_turn_stop_strategy import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

import jarvis_tools as tools
from config import CARTESIA_API_KEY, CARTESIA_VOICE_ID, DEEPGRAM_API_KEY, OPENAI_API_KEY
from core.awareness import AwarenessLoop, NotificationQueue
from core.context import SessionContext
from core.fact_extractor import fire_and_forget as extract_facts_bg
from core.profile import UserProfile
from core.response import filter_voice
from shared.mempalace_adapter import build_memory_context
from tools.github_cache import GitHubAccountCache
from voice.hud_server import broadcast as _hud_broadcast, start_hud_server as _start_hud_server
from voice.mute_strategies import PostSpeechMuteStrategy
from voice.system_prompt import (
    ACK_PHRASES as _ACK,
    EXIT_PHRASES,
    SYSTEM_PROMPT,
    build_system_prompt as _build_system_prompt_impl,
)

_SENTENCE_END = re.compile(r"[.!?…]+\s*")

_github_cache: GitHubAccountCache | None = None


def _build_system_prompt(profile: UserProfile, context: SessionContext) -> str:
    """Wrap the module-level GitHub cache into the turn-time system prompt."""
    return _build_system_prompt_impl(profile, context, _github_cache)


class JarvisProcessor(FrameProcessor):
    """Pipecat processor that drives one streaming LLM turn per user utterance.

    Responsibilities:
    - Split streaming LLM tokens into sentences and push each to TTS fast.
    - Run any mid-stream tool calls in background threads and speak results.
    - Keep session history bounded and inject MemPalace memory context.
    - Broadcast lifecycle events (listening/thinking/speaking/idle) to the HUD.
    """

    def __init__(
        self,
        api_key: str,
        context: SessionContext,
        profile: UserProfile,
        notification_queue: NotificationQueue,
    ) -> None:
        super().__init__()
        self._client = AsyncOpenAI(api_key=api_key)
        self._history: list[dict] = []
        self._context = context
        self._profile = profile
        self._notification_queue = notification_queue
        self._tool_calls_in_turn: list[str] = []
        self._last_reply: str = ""
        self._onboarding_active = False
        self._onboarding_index = 0
        self._onboarding_answers: dict[str, str] = {}

    async def _speak(self, text: str, direction) -> None:
        """Push a chunk of text to TTS if it contains any alphanumeric content."""
        if text and any(c.isalnum() for c in text):
            await self.push_frame(TextFrame(text=text), direction)

    async def _run_tool_bg(self, tool_name: str, tool_args: dict, direction) -> None:
        """Execute a tool off-thread, filter/summarise its output, then speak it."""
        self._tool_calls_in_turn.append(tool_name)
        print(f"[Tool] Running {tool_name}({tool_args}) in background...")
        result = await asyncio.to_thread(tools.execute, tool_name, tool_args)
        print(f"[Tool] {tool_name} done: {result[:100]}")

        spoken = filter_voice(result)
        if not spoken:
            return

        if any(spoken.startswith(p) for p in ("Error:", "Failed:", "That didn't work")):
            pass
        elif len(spoken) > 200:
            try:
                resp = await self._client.chat.completions.create(
                    model="gpt-4.1",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Convert this tool result into ONE short spoken sentence. "
                                "Max 15 words. No preamble. No IDs or raw numbers."
                            ),
                        },
                        {"role": "user", "content": spoken[:500]},
                    ],
                    max_tokens=40,
                    temperature=0.4,
                )
                spoken = resp.choices[0].message.content.strip()
            except Exception:
                spoken = spoken[:100]

        print(f"[JARVIS] {spoken}")
        await self._speak(spoken, direction)

    async def _handle_turn(self, user_text: str, direction) -> None:
        """Run one streaming LLM turn, push sentences to TTS, queue tool calls."""
        self._history.append({"role": "user", "content": user_text})
        self._tool_calls_in_turn = []

        if len(self._history) > 20:
            self._history = self._history[-20:]

        system_content = _build_system_prompt(self._profile, self._context)
        mem_ctx = build_memory_context(query_hint=user_text)
        if mem_ctx:
            system_content += mem_ctx
        messages = [{"role": "system", "content": system_content}] + self._history

        try:
            stream = await self._client.chat.completions.create(
                model="gpt-4.1",
                messages=messages,
                tools=tools.TOOLS,
                tool_choice="auto",
                max_tokens=300,
                temperature=0.7,
                stream=True,
            )
        except Exception as e:
            logger.error(f"LLM error: {e}")
            await self._speak("Something went wrong on my end, sir.", direction)
            return

        spoken_tokens: list[str] = []
        tool_calls_raw: dict[int, dict] = {}
        sentence_buf = ""

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            if delta.content:
                spoken_tokens.append(delta.content)
                sentence_buf += delta.content
                await _hud_broadcast("response_token", delta.content)
                while _SENTENCE_END.search(sentence_buf):
                    m = _SENTENCE_END.search(sentence_buf)
                    sentence = sentence_buf[: m.end()].strip()
                    sentence_buf = sentence_buf[m.end():]
                    if sentence:
                        await _hud_broadcast("speaking", sentence)
                        await self.push_frame(TextFrame(text=sentence), direction)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_raw:
                        tool_calls_raw[idx] = {"id": "", "name": "", "args": ""}
                    if tc.id:
                        tool_calls_raw[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_raw[idx]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_raw[idx]["args"] += tc.function.arguments

        if sentence_buf.strip():
            await self.push_frame(TextFrame(text=sentence_buf.strip()), direction)

        spoken_text = "".join(spoken_tokens).strip()
        if spoken_text:
            print(f"[JARVIS] {spoken_text}")
            self._history.append({"role": "assistant", "content": spoken_text})
        self._last_reply = spoken_text

        for tc in tool_calls_raw.values():
            name = tc["name"]
            try:
                args = json.loads(tc["args"]) if tc["args"] else {}
            except json.JSONDecodeError:
                args = {}

            print(f"[JARVIS] → tool: {name}({args})")
            await _hud_broadcast("tool_call", {"name": name, "args": args})

            if not spoken_text:
                ack = random.choice(_ACK)
                print(f"[JARVIS] {ack}")
                await self._speak(ack, direction)

            asyncio.ensure_future(self._run_tool_bg(name, args, direction))

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)

        from pipecat.frames.frames import VADUserStartedSpeakingFrame

        if isinstance(frame, VADUserStartedSpeakingFrame):
            await _hud_broadcast("listening")

        if not (isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM):
            await self.push_frame(frame, direction)
            return

        user_text = ""
        for msg in reversed(frame.context.messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    user_text = content.strip()
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            user_text = block.get("text", "").strip()
                            break
                break

        if not user_text:
            await self.push_frame(frame, direction)
            return

        if self._onboarding_active:
            from core.onboarding import (
                build_voice_onboarding_prompt,
                get_question_key,
                process_onboarding_answers,
            )

            key = get_question_key(self._onboarding_index)
            if key:
                self._onboarding_answers[key] = user_text
                print(f"[Onboarding] {key} = {user_text}")

            self._onboarding_index += 1
            next_q = build_voice_onboarding_prompt(self._onboarding_index)
            if next_q:
                await self._speak(next_q, direction)
            else:
                profile = process_onboarding_answers(self._onboarding_answers)
                self._profile = profile
                self._onboarding_active = False
                await self._speak(
                    f"All set, {profile.name}! I'll remember everything about you. "
                    "Now, how can I help?",
                    direction,
                )
            return

        pending = self._notification_queue.pop_high()
        if pending:
            for n in pending:
                print(f"[Awareness] {n.message}")
                await self._speak(n.message, direction)

        print(f"\n[You] {user_text}")
        await _hud_broadcast("transcript", user_text)
        await _hud_broadcast("thinking")

        if any(p in user_text.lower() for p in EXIT_PHRASES):
            await self._speak("Going to standby. Say Hey Jarvis when you need me, sir.", direction)
            return

        await self._handle_turn(user_text, direction)

        reply_text = self._last_reply or ""
        self._context.add_turn(user_text, "VoiceAgent", reply_text, self._tool_calls_in_turn)

        if reply_text:
            extract_facts_bg(user_text, reply_text)

        await _hud_broadcast("idle")


# STT keyword boosting helps Deepgram recognise technical terms that sound
# like common English words (e.g. "pipecat" heard as "pie cut").
_DEEPGRAM_KEYWORDS: list[str] = [
    "GitHub:5", "repo:5", "repository:3", "pull request:3",
    "langchain:5", "pipecat:5", "FastAPI:4", "PyTorch:4",
    "TensorFlow:4", "LangGraph:4", "CrewAI:4", "OpenAI:4",
    "DeepSeek:4", "Anthropic:4", "ChromaDB:4", "Ollama:4",
    "Hugging Face:3", "Next.js:3", "Tailwind:3", "Supabase:3",
    "track repo:5", "untrack:4", "check releases:4",
    "list tracked:4", "repo info:4", "star repo:3",
    "create issue:4", "create PR:4", "pull request:4",
    "akkupratap323:5", "akkupratap:5",
]


def _time_of_day(hour: int) -> str:
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    if hour < 21:
        return "evening"
    return "night"


async def run_pipeline() -> None:
    """Start the JARVIS voice pipeline (auth gate → wake word → pipecat loop)."""
    from utils import play_sound
    from voice.auth_gate import run_voice_auth_gate

    if not await run_voice_auth_gate():
        return

    play_sound("activated")

    from wake_word import WakeWordDetector

    detector = WakeWordDetector(threshold=0.5)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, detector.wait_for_wake_word)

    from core.onboarding import build_voice_onboarding_prompt, needs_onboarding

    _needs_onboarding = needs_onboarding()

    context = SessionContext()
    profile = UserProfile.load()
    notification_queue = NotificationQueue()
    awareness = AwarenessLoop(notification_queue, profile.timezone)
    await awareness.start()

    global _github_cache
    if profile.github_username:
        _github_cache = GitHubAccountCache(profile.github_username)
        asyncio.ensure_future(asyncio.to_thread(_github_cache.fetch))
        asyncio.ensure_future(_github_cache.start_refresh_loop())

    stt = DeepgramSTTService(
        api_key=DEEPGRAM_API_KEY,
        ttfs_p99_latency=0.5,
        settings=DeepgramSTTSettings(
            language="en",
            model="nova-2",
            smart_format=True,
            keywords=_DEEPGRAM_KEYWORDS,
        ),
    )

    tts = CartesiaTTSService(
        api_key=CARTESIA_API_KEY,
        settings=CartesiaTTSSettings(voice=CARTESIA_VOICE_ID),
        text_aggregation_mode=TextAggregationMode.TOKEN,
    )

    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            output_device_index=1,
            audio_out_sample_rate=24000,
        )
    )

    system_content = _build_system_prompt(profile, context)
    llm_context = LLMContext()
    llm_context.add_message({"role": "system", "content": system_content})

    user_agg, assistant_agg = LLMContextAggregatorPair(
        llm_context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=0.7,
                    start_secs=0.2,
                    stop_secs=0.2,
                    min_volume=0.6,
                )
            ),
            user_mute_strategies=[
                MuteUntilFirstBotCompleteUserMuteStrategy(),
                PostSpeechMuteStrategy(post_speech_secs=1.0),
            ],
            user_turn_strategies=UserTurnStrategies(
                start=[
                    VADUserTurnStartStrategy(),
                    MinWordsUserTurnStartStrategy(min_words=1),
                ],
                stop=[
                    TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3()),
                    SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=1.0),
                ],
            ),
        ),
    )

    jarvis = JarvisProcessor(
        api_key=OPENAI_API_KEY,
        context=context,
        profile=profile,
        notification_queue=notification_queue,
    )

    if _needs_onboarding:
        jarvis._onboarding_active = True
        jarvis._onboarding_index = 0

    pipeline = Pipeline([
        transport.input(),
        stt,
        user_agg,
        jarvis,
        tts,
        transport.output(),
        assistant_agg,
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=False,
            allow_interruptions=True,
            audio_out_sample_rate=24000,
        ),
    )

    await _start_hud_server()
    runner = PipelineRunner(handle_sigint=True)

    async def _startup_briefing() -> None:
        """Speak an onboarding prompt on first run, else a contextual briefing."""
        await asyncio.sleep(1.0)

        if _needs_onboarding:
            print("\n[JARVIS] First run detected. Starting onboarding...\n")
            first_q = build_voice_onboarding_prompt(0)
            greeting = (
                "Hello! I'm JARVIS, your personal AI assistant. "
                "Before we get started, I need to know a few things about you. "
                f"{first_q}"
            )
            onboarding_ctx = LLMContext()
            onboarding_ctx.add_message({"role": "system", "content": SYSTEM_PROMPT})
            onboarding_ctx.add_message({"role": "assistant", "content": greeting})
            await task.queue_frame(LLMContextFrame(context=onboarding_ctx))
            return

        print("\n[JARVIS] Online. Running startup briefing...\n")

        from datetime import datetime

        now = datetime.now()
        time_ctx = _time_of_day(now.hour)
        day_name = now.strftime("%A")
        date_str = now.strftime("%B %d, %Y")

        def _get_emails() -> str:
            try:
                from tools.google import gmail_read
                return gmail_read(max_results=2)
            except Exception as e:
                return f"Could not fetch emails: {e}"

        def _get_calendar() -> str:
            try:
                from tools.google import calendar_list
                return calendar_list(days=1)
            except Exception as e:
                return f"Could not fetch calendar: {e}"

        emails, cal = await asyncio.gather(
            asyncio.to_thread(_get_emails),
            asyncio.to_thread(_get_calendar),
        )

        def _open_antigravity() -> None:
            from tools.apps import open_app
            open_app("Antigravity")

        asyncio.ensure_future(asyncio.to_thread(_open_antigravity))

        briefing_prompt = f"""It is {time_ctx} on {day_name}, {date_str}.

User name: {profile.name}

CALENDAR TODAY:
{cal}

LATEST 2 EMAILS:
{emails}

Give {profile.name} a smart startup briefing in 4-5 short spoken sentences:
1. Warm {time_ctx} greeting with the day, address them by name
2. What's on the calendar today (or say clear if nothing)
3. Quick summary of the 2 emails (sender + what it's about)
4. A sharp, motivating piece of advice relevant to {day_name} {time_ctx} — make it feel personal and energising, not generic

Keep it natural, warm, conversational. Voice only — no bullet points or lists."""

        startup_context = LLMContext()
        startup_context.add_message(
            {"role": "system", "content": SYSTEM_PROMPT + profile.build_profile_block()}
        )
        startup_context.add_message({"role": "user", "content": briefing_prompt})
        await task.queue_frame(LLMContextFrame(context=startup_context))

    asyncio.ensure_future(_startup_briefing())
    await runner.run(task)
