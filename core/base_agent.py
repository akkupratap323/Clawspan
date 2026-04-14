"""BaseAgent - shared agent skeleton with tool-calling loop."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from core.llm import get_client, get_model
from core.prompts import PERSONALITY, RESPONSE_RULES
from core.profile import UserProfile
from core.context import SessionContext
from core.response import filter_text
from shared.memory import build_memory_context, save_session_context

# DSML leak cleanup
_THINK_RE = re.compile(r'<thinking>.*?</thinking>', re.DOTALL)
_FUNC_TAG_RE = re.compile(r'</?function[^>]*>.*?(?:</function>|$)', re.DOTALL)
_DSML_BLOCK_RE = re.compile(
    r'<DSMLfunction_calls>.*?</DSML/function_calls>', re.DOTALL,
)
_DSML_TAG_RE = re.compile(r'</?DSML[^>]*>', re.DOTALL)
_DSML_INVOKE_RE = re.compile(
    r'<DSMLinvoke name="(\w+)">(.*?)</DSMLinvoke>', re.DOTALL,
)
_DSML_PARAM_RE = re.compile(
    r'<DSMLparameter name="(\w+)"[^>]*>(.*?)</DSMLparameter>', re.DOTALL,
)

# Auto-extraction: keywords that suggest personal facts worth saving
_PERSONAL_KEYWORDS = re.compile(
    r'\b(my name is|i am|i live|i work|my favorite|i like|i love|i hate|'
    r'i prefer|remind me|remember that|my birthday|my email|my phone|'
    r'my address|my wife|my husband|my daughter|my son|my dog|my cat|'
    r'i\'m from|i was born|my job|my hobby|my schedule|call me|'
    r'my company|i founded|we raised|our product|i\'m building|i\'m working on|'
    r'my project|my startup|my team|my goal|my plan|my deadline|'
    r'my university|my college|i study|i\'m studying|i graduated|'
    r'my age|i turned|i\'m \d+|born in|my timezone|i\'m in|i\'m at|'
    r'my boss|my manager|my colleague|my co-founder|my investor|'
    r'always remember|never forget|important:|note:|fyi:|'
    r'my api key|my token|my password|my username)\b',
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    """Strip think tags, DSML, and function-tag leaks from LLM output."""
    text = _THINK_RE.sub("", text)
    text = _FUNC_TAG_RE.sub("", text)
    text = _DSML_BLOCK_RE.sub("", text)
    text = _DSML_TAG_RE.sub("", text)
    return text.strip()


def _extract_dsml(text: str) -> tuple[str, dict[str, str]] | None:
    """Try to recover a DSML tool-call leak from raw text."""
    m = _DSML_INVOKE_RE.search(text)
    if not m:
        return None
    fn_name = m.group(1)
    args = {
        pm.group(1): pm.group(2).strip()
        for pm in _DSML_PARAM_RE.finditer(m.group(2))
    }
    return fn_name, args


async def _auto_extract_facts(user_input: str, reply: str) -> None:
    """Extract personal facts from conversation and save to MemPalace.

    Only fires when user_input contains personal keywords.
    Uses DeepSeek to extract structured facts, then files them.
    Runs async — does not block the response.
    """
    if not _PERSONAL_KEYWORDS.search(user_input):
        return

    try:
        prompt = (
            "Extract personal facts from this exchange. Return a JSON array of objects "
            "with keys: 'key' (short label), 'value' (the fact), 'type' (person/preference/fact).\n"
            "If no personal facts, return: []\n"
            "ONLY output JSON, nothing else.\n\n"
            f"User: {user_input[:200]}\n"
            f"Assistant: {reply[:200]}"
        )
        response = await get_client().chat.completions.create(
            model=get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.0,
        )
        text = (response.choices[0].message.content or "").strip()

        # Parse JSON array
        if text.startswith("["):
            facts = json.loads(text)
        else:
            # Try to find JSON array in response
            m = re.search(r'\[.*\]', text, re.DOTALL)
            if m:
                facts = json.loads(m.group(0))
            else:
                return

        if not facts:
            return

        from shared.mempalace_adapter import save_fact, add_entity, add_triple

        for fact in facts[:3]:  # Max 3 facts per turn
            key = fact.get("key", "")
            value = fact.get("value", "")
            fact_type = fact.get("type", "fact")
            if not key or not value:
                continue

            # Save to ChromaDB + KG
            save_fact(key, value, wing="personal", room=fact_type)

            # If it's a person, add entity to KG
            if fact_type == "person":
                add_entity(value, "person")
                add_triple(key, "is", value)

            print(f"[Memory] Auto-saved: {key} = {value}", flush=True)

    except Exception as e:
        # Never let extraction errors break the main flow
        print(f"[Memory] Auto-extract error (non-fatal): {e}", flush=True)


class BaseAgent:
    """Abstract base for all Clawspan agents.

    Subclass contract:
        name:        str                          — e.g. "SystemAgent"
        SYSTEM_PROMPT: str                        — agent-specific instructions
        TOOLS:       list[dict]                   — OpenAI function schemas
        TOOL_MAP:    dict[str, Callable[[dict], str]]  — name → executor
    """

    name: str = "BaseAgent"
    SYSTEM_PROMPT: str = ""
    TOOLS: list[dict[str, Any]] = []
    TOOL_MAP: dict[str, Callable[[dict], str]] = {}

    # Tuning knobs subclasses can override
    max_history: int = 20
    temperature: float = 0.3
    max_tokens: int = 1024
    max_tool_rounds: int = 5

    def __init__(
        self,
        context: SessionContext | None = None,
        profile: UserProfile | None = None,
    ) -> None:
        self._context = context
        self._profile = profile
        self._router = None

        # Static base: personality + agent instructions + rules (no memory yet)
        # Memory is injected fresh on every think() call
        self._base_prompt = (
            PERSONALITY + "\n\n"
            + self.SYSTEM_PROMPT + "\n\n"
            + RESPONSE_RULES
        )
        self._conversation: list[dict] = [
            {"role": "system", "content": self._base_prompt},
        ]
        print(f"[{self.name}] Ready.", flush=True)

    def _build_system_prompt(self, query_hint: str = "") -> str:
        """Build a fresh system prompt with live memory, profile, and context.

        Called on every think() turn so newly-saved facts are visible immediately.
        """
        mem_context = build_memory_context(query_hint=query_hint)
        prompt = self._base_prompt + mem_context
        if self._profile:
            prompt += self._profile.build_profile_block()
        if self._context:
            prompt += self._context.build_context_prompt()
        return prompt

    # ── Tool execution ───────────────────────────────────────────────────────

    def _execute_tool(self, fn_name: str, fn_args: dict) -> str:
        handler = self.TOOL_MAP.get(fn_name)
        if handler is None:
            return f"Unknown tool: {fn_name}"
        try:
            return handler(fn_args)
        except Exception as e:
            return f"Tool error ({fn_name}): {e}"

    # ── Delegation ───────────────────────────────────────────────────────────

    async def delegate(self, agent_name: str, task: str) -> str:
        """Delegate a sub-task to another agent via the router."""
        if hasattr(self, '_router') and self._router:
            ctx_desc = f"Delegated from {self.name}"
            return await self._router.run_subtask(agent_name, task, ctx_desc)
        return f"Cannot delegate — no router attached to {self.name}"

    # ── LLM call ─────────────────────────────────────────────────────────────

    async def _call_llm(
        self, *, with_tools: bool = True, max_tokens: int | None = None,
    ):
        kwargs: dict[str, Any] = {
            "model": get_model(),
            "messages": self._conversation,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature,
        }
        if with_tools and self.TOOLS:
            kwargs["tools"] = self.TOOLS
            kwargs["tool_choice"] = "auto"
        try:
            return await get_client().chat.completions.create(**kwargs)
        except Exception:
            if with_tools:
                return await self._call_llm(with_tools=False, max_tokens=max_tokens)
            raise

    # ── Main think loop ──────────────────────────────────────────────────────

    async def think(self, user_input: str, context: str = "") -> str:
        """Process user input and return a spoken response."""
        # Refresh system prompt with live memory on every turn
        self._conversation[0]["content"] = self._build_system_prompt(query_hint=user_input)

        # Inject session context if provided separately
        if context:
            self._conversation.append({"role": "user", "content": f"{context}\n\n{user_input}"})
        else:
            self._conversation.append({"role": "user", "content": user_input})

        # Trim history
        if len(self._conversation) > self.max_history + 1:
            self._conversation = (
                [self._conversation[0]] + self._conversation[-(self.max_history):]
            )

        for _ in range(self.max_tool_rounds):
            response = await self._call_llm(with_tools=True)
            message = response.choices[0].message

            # ── Native tool calls ────────────────────────────────────────
            if message.tool_calls:
                self._conversation.append(message)
                for tc in message.tool_calls:
                    fn_name = tc.function.name
                    try:
                        fn_args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {}
                    print(f"[{self.name}] {fn_name}({list(fn_args.keys())})", flush=True)
                    result = self._execute_tool(fn_name, fn_args)
                    self._conversation.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                continue

            # ── DSML leak recovery ───────────────────────────────────────
            raw = message.content or ""
            dsml = _extract_dsml(raw)
            if dsml:
                fn_name, fn_args = dsml
                preamble = _clean(raw)
                result = self._execute_tool(fn_name, fn_args)
                self._conversation.append({
                    "role": "assistant", "content": preamble or f"Calling {fn_name}.",
                })
                self._conversation.append({
                    "role": "user", "content": f"[Tool result]: {result}",
                })
                continue

            # ── Final text response ──────────────────────────────────────
            reply = _clean(raw) or "Done, sir."
            # Apply response filter
            filtered = filter_text(reply, user_input)
            if not filtered:
                filtered = "Done, sir."
            self._conversation.append({"role": "assistant", "content": reply})
            save_session_context(
                self._conversation, self.SYSTEM_PROMPT, user_input, reply,
            )

            # Auto-extract personal facts (async, non-blocking)
            try:
                import asyncio
                asyncio.ensure_future(_auto_extract_facts(user_input, reply))
            except Exception:
                pass

            return filtered

        # Exhausted tool rounds
        response = await self._call_llm(with_tools=False, max_tokens=256)
        reply = _clean(response.choices[0].message.content or "Done, sir.")
        filtered = filter_text(reply, user_input)
        self._conversation.append({"role": "assistant", "content": reply})
        return filtered or "Done, sir."
