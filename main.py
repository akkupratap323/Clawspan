"""
Clawspan — Your Iron Man AI Assistant

Usage:
    python main.py          # Voice mode (default) — wake word → voice pipeline
    python main.py --text   # Text mode — brain router in terminal
"""

import asyncio
import sys

from utils import print_banner


async def run_voice() -> None:
    """Start the voice pipeline (Mic → STT → GPT → TTS → Speaker)."""
    from clawspan_pipeline import run_pipeline
    await run_pipeline()


async def run_text() -> None:
    """Start the brain router in text mode for testing."""
    from agents.system_agent import SystemAgent
    from agents.research_agent import ResearchAgent
    from agents.writer_agent import WriterAgent
    from agents.calendar_agent import CalendarAgent
    from agents.coding_agent import CodingAgent
    from agents.claude_agent import ClaudeAgent
    from agents.deploy_monitor_agent import DeployMonitorAgent
    from agents.github_monitor_agent import GitHubMonitorAgent
    from agents.github_action_agent import GitHubActionAgent
    from core.router import BrainRouter
    from core.github_router import GitHubRouter
    from core.context import SessionContext
    from core.profile import UserProfile
    from core.awareness import AwarenessLoop, NotificationQueue
    from core.onboarding import needs_onboarding, run_text_onboarding
    from core.auth import is_setup, check, setup_password, lockout_remaining

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
            pw = input("[Auth] Passphrase: ").strip()
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
                pw = input("[Auth] Enter passphrase: ").strip()
                pw2 = input("[Auth] Confirm passphrase: ").strip()
                if pw and pw == pw2:
                    setup_password(pw)
                    print("[Auth] Passphrase set.", flush=True)
                else:
                    print("[Auth] Didn't match. No password set.", flush=True)
        except (EOFError, KeyboardInterrupt):
            pass

    # First-run onboarding — ask personal details
    if needs_onboarding():
        profile = await run_text_onboarding()
    else:
        profile = UserProfile.load()

    # Shared context + profile
    context = SessionContext()
    notification_queue = NotificationQueue()

    # Start awareness loop
    awareness = AwarenessLoop(notification_queue, profile.timezone)
    await awareness.start()

    # GitHub agents + sub-router
    github_monitor = GitHubMonitorAgent(context=context, profile=profile)
    github_action = GitHubActionAgent(context=context, profile=profile)
    github_router = GitHubRouter(github_monitor, github_action)

    agents = {
        "system": SystemAgent(),
        "research": ResearchAgent(),
        "writer": WriterAgent(),
        "calendar": CalendarAgent(),
        "coding": CodingAgent(),
        "claude": ClaudeAgent(),
        "deploy": DeployMonitorAgent(context=context, profile=profile),
    }
    brain = BrainRouter(
        agents,
        default_route="system",
        context=context,
        profile=profile,
        notification_queue=notification_queue,
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
