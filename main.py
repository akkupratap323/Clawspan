"""
Clawspan — Your Iron Man AI Assistant

Usage:
    python main.py          # Voice mode (default) — wake word → voice pipeline
    python main.py --text   # Text mode — brain router in terminal
"""

import os
import asyncio
import sys

# macOS 26.x xzone allocator crashes inside OpenSSL CRYPTO_malloc (SIGTRAP).
# Must be set before any SSL/TLS import. Has no effect on other platforms.
os.environ.setdefault("MallocNanoZone", "0")
from getpass import getpass

from utils import print_banner


async def run_voice() -> None:
    """Start the voice pipeline (Mic → STT → GPT → TTS → Speaker)."""
    from clawspan_pipeline import run_pipeline
    await run_pipeline()


async def run_text() -> None:
    """Start the brain router in text mode for testing."""
    import importlib
    import traceback

    from core.context import SessionContext
    from core.profile import UserProfile
    from core.auth import is_setup, check, setup_password, lockout_remaining
    from core.onboarding import needs_onboarding, run_text_onboarding

    # Lazy import agents with graceful degradation
    missing_deps = {}
    optional_modules = {
        "agents.system_agent": "SystemAgent",
        "agents.research_agent": "ResearchAgent",
        "agents.writer_agent": "WriterAgent",
        "agents.calendar_agent": "CalendarAgent",
        "agents.deepcoder_agent": "DeepCoderAgent",
        "agents.deploy_monitor_agent": "DeployMonitorAgent",
        "core.router": "BrainRouter",
        "core.github_router": "GitHubRouter",
        "core.awareness": "AwarenessLoop, NotificationQueue",
    }

    imported = {}
    for module, classes in optional_modules.items():
        try:
            mod = importlib.import_module(module)
            for cls_name in classes.split(", "):
                imported[cls_name] = getattr(mod, cls_name)
        except ImportError as e:
            missing_deps[module] = str(e)

    if missing_deps:
        print("\n[Warning] Some modules failed to import:", flush=True)
        for mod, err in missing_deps.items():
            print(f"  - {mod}: {err}", flush=True)
        print("Install missing dependencies: pip install -r requirements.txt\n", flush=True)

    SystemAgent = imported.get("SystemAgent")
    ResearchAgent = imported.get("ResearchAgent")
    WriterAgent = imported.get("WriterAgent")
    CalendarAgent = imported.get("CalendarAgent")
    DeepCoderAgent = imported.get("DeepCoderAgent")
    DeployMonitorAgent = imported.get("DeployMonitorAgent")
    BrainRouter = imported.get("BrainRouter")
    GitHubRouter = imported.get("GitHubRouter")
    AwarenessLoop = imported.get("AwarenessLoop")
    NotificationQueue = imported.get("NotificationQueue")

    # Google OAuth — trigger on first run so browser opens before conversation starts
    from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        try:
            from auth.google import get_credentials
            await asyncio.to_thread(get_credentials)
            print("[Auth] Google credentials ready.", flush=True)
        except Exception as e:
            print(f"[Auth] Google auth skipped: {e}", flush=True)

    # ── Password gate ──────────────────────────────────────────────────
    if is_setup():
        print("\n[Auth] Access verification required.", flush=True)
        for attempt in range(3):
            remaining = lockout_remaining()
            if remaining > 0:
                print(f"[Auth] Locked. Wait {remaining}s.", flush=True)
                import asyncio
                await asyncio.sleep(remaining)
                continue
            pw = getpass("[Auth] Passphrase: ").strip()
            result = check(pw)
            if result == "ok":
                print("[Auth] Identity confirmed. Welcome back.", flush=True)
                break
            elif result == "locked":
                print(f"[Auth] Access denied. Locked.", flush=True)
                return
            else:
                print(f"[Auth] Wrong. {2 - attempt} attempts left.", flush=True)
        else:
            print("[Auth] All attempts exhausted. Goodbye.", flush=True)
            return
    elif not needs_onboarding():
        # Not onboarded yet but not first run — offer to set password
        print("\n[Auth] No passphrase set. Set one now? (y/n)", flush=True)
        try:
            ans = input("> ").strip().lower()
            if ans in ("y", "yes"):
                pw = getpass("[Auth] Enter passphrase: ").strip()
                pw2 = getpass("[Auth] Confirm passphrase: ").strip()
                if pw and pw == pw2:
                    setup_password(pw)
                    print("[Auth] Passphrase set.", flush=True)
                else:
                    print("[Auth] Didn't match. No password set.", flush=True)
        except (EOFError, KeyboardInterrupt):
            pass

    # Google OAuth — trigger on first run so browser opens before conversation starts
    from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        try:
            from auth.google import get_credentials
            await asyncio.to_thread(get_credentials)
            print("[Auth] Google credentials ready.", flush=True)
        except Exception as _google_err:
            print(f"[Auth] Google auth skipped: {_google_err}", flush=True)

    # First-run onboarding — ask personal details
    if needs_onboarding():
        profile = await run_text_onboarding()
    else:
        profile = UserProfile.load()

    # Shared context + profile
    context = SessionContext()
    notification_q = NotificationQueue() if NotificationQueue else None

    # Start awareness loop
    if AwarenessLoop and notification_q:
        awareness = AwarenessLoop(notification_q, profile.timezone)
        await awareness.start()
    else:
        print("[Warning] AwarenessLoop not available — skipping background monitoring.\n", flush=True)

    agents = {}
    if SystemAgent:
        agents["system"] = SystemAgent()
    if ResearchAgent:
        agents["research"] = ResearchAgent()
    if WriterAgent:
        agents["writer"] = WriterAgent()
    if CalendarAgent and notification_q:
        agents["calendar"] = CalendarAgent(notification_queue=notification_q)
    if DeepCoderAgent:
        agents["coding"] = DeepCoderAgent()
        agents["deepcoder"] = DeepCoderAgent()
    if DeployMonitorAgent:
        agents["deploy"] = DeployMonitorAgent(context=context, profile=profile)

    if not agents:
        print("[Error] No agents available. Install dependencies and retry.", flush=True)
        return

    github_router = None
    if GitHubRouter:
        from agents.github_monitor_agent import GitHubMonitorAgent
        from agents.github_action_agent import GitHubActionAgent
        github_monitor = GitHubMonitorAgent(context=context, profile=profile)
        github_action = GitHubActionAgent(context=context, profile=profile)
        github_router = GitHubRouter(github_monitor, github_action)

    brain = BrainRouter(
        agents,
        default_route="system",
        context=context,
        profile=profile,
        notification_queue=notification_q,
        github_router=github_router,
    )

    print(f"\n[Clawspan] Text mode ready. Profile: {profile.name}. Type your commands (Ctrl+C to exit).\n")
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Clawspan] Goodbye, sir.")
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("[Clawspan] Goodbye, sir.")
            break

        response = await brain.think(user_input)
        print(f"Clawspan: {response}\n")


async def main() -> None:
    print_banner()

    if "--text" in sys.argv:
        await run_text()
    else:
        await run_voice()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Clawspan] Shutting down. Goodbye, sir.")
        sys.exit(0)


def cli() -> None:
    """Entry point for the `clawspan` CLI command (pyproject.toml scripts)."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Clawspan] Shutting down. Goodbye, sir.")
        sys.exit(0)
