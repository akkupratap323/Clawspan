"""First-run onboarding — Clawspan asks key personal questions on first startup.

Detects first run by checking if MemPalace has any personal memories.
Collects: name, work, key people, style preference, important notes.
Saves everything to: UserProfile, MemPalace (ChromaDB + KG), Identity file.

Works in both text mode (interactive input) and voice mode (via TTS/STT).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict

from core.profile import UserProfile, PROFILE_PATH
from shared.mempalace_adapter import (
    save_fact,
    add_entity,
    add_triple,
    set_identity,
    get_identity,
    _get_collection,
    MEMPALACE_DIR,
)

ONBOARDING_MARKER = os.path.join(MEMPALACE_DIR, ".onboarded")

# Questions for onboarding — each is (key, question, follow_up_hint)
QUESTIONS = [
    # ── Basic identity (original 5) ─────────────────────────────────────
    (
        "name",
        "Hey boss — what should I call you?",
        "Just your first name or nickname is fine.",
    ),
    (
        "work",
        "What do you do for work? Just a brief description.",
        "e.g. software engineer, student, designer, entrepreneur...",
    ),
    (
        "people",
        "Any key people I should know about? Family, partner, close colleagues?",
        "e.g. 'My wife Priya, brother Rahul, boss Amit'",
    ),
    (
        "style",
        "How do you like me to talk? Casual and witty, formal, or ultra-brief?",
        "casual / formal / terse",
    ),
    (
        "notes",
        "Anything else important I should remember? Preferences, routines, reminders?",
        "e.g. 'I'm vegetarian', 'I wake up at 6am', 'Remind me to exercise'",
    ),
    # ── Rich personality (deep data — runs only once) ───────────────────
    (
        "skills",
        "What are your main skills or areas of expertise?",
        "e.g. Python, machine learning, UI design, project management...",
    ),
    (
        "tech_stack",
        "What tech stack or tools do you use daily?",
        "e.g. VS Code, React, FastAPI, Docker, PostgreSQL...",
    ),
    (
        "work_style",
        "How do you prefer to work? Solo deep focus, or collaborative?",
        "e.g. 'I like deep focus blocks in the morning, meetings afternoon'",
    ),
    (
        "goals",
        "What are your big goals right now? Career, projects, learning?",
        "e.g. 'Building a startup', 'Learning Rust', 'Getting promoted'",
    ),
    (
        "learning_interests",
        "What topics are you actively learning about?",
        "e.g. AI/ML, web3, systems design, music production...",
    ),
    (
        "content_interests",
        "What kind of content do you follow? News, tech, science, finance?",
        "e.g. 'Tech news, AI papers, stock markets, space'",
    ),
    (
        "music_taste",
        "What music do you listen to?",
        "e.g. lo-fi, rock, classical, hip-hop, Bollywood...",
    ),
    (
        "daily_routine",
        "Describe a typical day — wake time, work blocks, wind-down?",
        "e.g. 'Wake 7am, deep work 9-12, meetings afternoon, gym 6pm'",
    ),
]


def needs_onboarding() -> bool:
    """Check if this is a first run (no onboarding done yet)."""
    return not os.path.exists(ONBOARDING_MARKER)


def _mark_onboarded() -> None:
    """Write marker file so onboarding doesn't run again."""
    os.makedirs(MEMPALACE_DIR, exist_ok=True)
    from datetime import datetime
    with open(ONBOARDING_MARKER, "w") as f:
        f.write(datetime.now().isoformat())


def process_onboarding_answers(answers: dict[str, str]) -> UserProfile:
    """Process collected answers and save to all systems.

    Args:
        answers: dict with keys matching QUESTIONS[i][0] — name, work, people, style, notes,
                 skills, tech_stack, work_style, goals, learning_interests,
                 content_interests, music_taste, daily_routine

    Returns:
        The configured UserProfile.
    """
    name = answers.get("name", "").strip() or "boss"
    work = answers.get("work", "").strip()
    people_raw = answers.get("people", "").strip()
    style_raw = answers.get("style", "casual").strip().lower()
    notes = answers.get("notes", "").strip()

    # ── Rich personality fields ────────────────────────────────────────
    skills_raw = answers.get("skills", "").strip()
    tech_stack = answers.get("tech_stack", "").strip()
    work_style = answers.get("work_style", "").strip()
    goals_raw = answers.get("goals", "").strip()
    learning_raw = answers.get("learning_interests", "").strip()
    content_raw = answers.get("content_interests", "").strip()
    music_taste = answers.get("music_taste", "").strip()
    daily_routine = answers.get("daily_routine", "").strip()

    # Normalize style
    style = "casual"
    if "formal" in style_raw:
        style = "formal"
    elif "terse" in style_raw or "brief" in style_raw:
        style = "terse"

    # ── 1. Save to UserProfile ──────────────────────────────────────────
    profile = UserProfile.load()
    profile.name = name
    profile.communication_style = style

    # Parse personality list fields
    profile.skills = [s.strip() for s in skills_raw.split(",") if s.strip()] if skills_raw else []
    profile.tech_stack = tech_stack
    profile.work_style = work_style
    profile.goals = [g.strip() for g in goals_raw.split(",") if g.strip()] if goals_raw else []
    profile.learning_interests = [l.strip() for l in learning_raw.split(",") if l.strip()] if learning_raw else []
    profile.content_interests = content_raw
    profile.music_taste = music_taste
    profile.daily_routine = daily_routine

    # Parse people into contacts
    contacts = _parse_people(people_raw)
    for person_name, relationship in contacts:
        profile.key_contacts[person_name.lower()] = relationship

    profile.save()
    print(f"[Onboarding] Profile saved: {profile.name}, style={profile.communication_style}")

    # ── 2. Save to MemPalace (ChromaDB + KG) ───────────��────────────────
    save_fact("user_name", name, wing="personal", room="identity", importance=5)

    if work:
        save_fact("user_work", work, wing="personal", room="identity", importance=4)

    if notes:
        save_fact("user_notes", notes, wing="personal", room="preferences", importance=4)

    # Save rich personality to MemPalace
    if skills_raw:
        save_fact("user_skills", skills_raw, wing="personal", room="skills", importance=5)
    if tech_stack:
        save_fact("user_tech_stack", tech_stack, wing="personal", room="tech", importance=5)
    if work_style:
        save_fact("user_work_style", work_style, wing="personal", room="work_style", importance=4)
    if goals_raw:
        save_fact("user_goals", goals_raw, wing="personal", room="goals", importance=5)
    if learning_raw:
        save_fact("user_learning", learning_raw, wing="personal", room="learning", importance=4)
    if content_raw:
        save_fact("user_content", content_raw, wing="personal", room="interests", importance=4)
    if music_taste:
        save_fact("user_music", music_taste, wing="personal", room="music", importance=3)
    if daily_routine:
        save_fact("user_routine", daily_routine, wing="personal", room="routine", importance=4)

    # Add user as entity in KG
    add_entity(name, "person", {"role": "user", "work": work})

    if work:
        add_triple(name, "works_as", work)

    # Process people → KG entities + triples
    for person_name, relationship in contacts:
        add_entity(person_name, "person")
        add_triple(name, relationship, person_name)
        save_fact(
            f"person_{person_name.lower()}",
            f"{person_name} is {name}'s {relationship}",
            wing="personal",
            room="people",
            importance=4,
        )
    print(f"[Onboarding] Saved {len(contacts)} contacts to KG")

    # ── 3. Update identity file ─────────────────────────────────────────
    people_str = ""
    if contacts:
        people_lines = [f"{pname} ({rel})" for pname, rel in contacts]
        people_str = f"\nKey people: {', '.join(people_lines)}"

    work_str = f"\n{name} works as: {work}" if work else ""
    notes_str = f"\nNotes: {notes}" if notes else ""

    identity = (
        f"I am Clawspan, a personal AI assistant for {name}.\n"
        f"Running on macOS. Casual, warm, witty. Always address {name} as 'boss'.\n"
        f"Communication style: {style}.{work_str}{people_str}{notes_str}\n"
        f"I remember everything and learn from every conversation."
    )
    set_identity(identity)
    print(f"[Onboarding] Identity file updated")

    # ── 4. Mark as done ─────────────────────────────────────────────────
    _mark_onboarded()
    print(f"[Onboarding] Complete for {name}")

    return profile


def _parse_people(raw: str) -> list[tuple[str, str]]:
    """Parse free-text people input into (name, relationship) pairs.

    Handles formats like:
        'My wife Priya, brother Rahul, boss Amit'
        'Priya (wife), Rahul (brother)'
        'wife: Priya, brother: Rahul'
    """
    if not raw:
        return []

    results = []
    # Split by comma or 'and'
    import re
    parts = re.split(r'[,;]|\band\b', raw)

    relationship_words = {
        "wife", "husband", "partner", "girlfriend", "boyfriend",
        "mother", "mom", "father", "dad", "brother", "sister",
        "son", "daughter", "friend", "boss", "colleague", "coworker",
        "uncle", "aunt", "cousin", "grandma", "grandpa",
    }

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Try "relationship name" format: "my wife Priya"
        m = re.match(
            r"(?:my\s+)?(\w+)\s+(.+)", part, re.IGNORECASE,
        )
        if m:
            word1 = m.group(1).lower()
            rest = m.group(2).strip()
            if word1 in relationship_words:
                results.append((rest.title(), word1))
                continue

        # Try "name (relationship)" format: "Priya (wife)"
        m = re.match(r"(.+?)\s*\((\w+)\)", part)
        if m:
            results.append((m.group(1).strip().title(), m.group(2).lower()))
            continue

        # Try "relationship: name" format: "wife: Priya"
        m = re.match(r"(\w+)\s*:\s*(.+)", part)
        if m:
            rel = m.group(1).lower()
            name = m.group(2).strip()
            if rel in relationship_words:
                results.append((name.title(), rel))
                continue

        # Fallback: just a name, relationship unknown
        clean = part.strip().title()
        if clean and len(clean) > 1:
            results.append((clean, "contact"))

    return results


async def run_text_onboarding() -> UserProfile:
    """Interactive text-mode onboarding. Asks questions via terminal input."""
    print("\n" + "=" * 55)
    print("  Clawspan — First-Time Setup")
    print("  I need to know a few things about you to get started.")
    print("=" * 55 + "\n")

    answers: dict[str, str] = {}

    for key, question, hint in QUESTIONS:
        print(f"  {question}")
        print(f"  ({hint})")
        try:
            answer = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  [Skipped remaining questions]")
            break
        answers[key] = answer
        print()

    profile = process_onboarding_answers(answers)

    print("=" * 55)
    print(f"  All set, {profile.name}! I'll remember everything.")
    print("=" * 55 + "\n")

    return profile


def build_voice_onboarding_prompt(question_index: int = 0) -> str | None:
    """Get the next onboarding question for voice mode.

    Returns the question text, or None if all questions asked.
    """
    if question_index >= len(QUESTIONS):
        return None
    key, question, hint = QUESTIONS[question_index]
    return question


def get_question_key(question_index: int) -> str | None:
    """Get the key for a question by index."""
    if question_index >= len(QUESTIONS):
        return None
    return QUESTIONS[question_index][0]


def total_questions() -> int:
    """Total number of onboarding questions."""
    return len(QUESTIONS)
