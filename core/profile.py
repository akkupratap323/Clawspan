"""UserProfile — persistent user identity.

Loads from ~/.clawspan_profile.json at startup.
Injected into EVERY agent's system prompt for personalization.
Auto-learns preferences from interactions.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any

PROFILE_PATH = os.path.expanduser("~/.clawspan_profile.json")

DEFAULT_PROFILE = {
    "name": "Boss",
    "timezone": "UTC",
    "wake_time": "07:00",
    "work_hours": {"start": "09:00", "end": "18:00"},
    "preferred_browser": "Chrome",
    "preferred_editor": "VS Code",
    "preferred_music_app": "YouTube Music",
    "communication_style": "casual",  # casual | formal | terse
    "key_contacts": {},  # {"name": "email@example.com"}
}


@dataclass
class UserProfile:
    name: str = "Boss"
    timezone: str = "UTC"
    wake_time: str = "07:00"
    work_hours: dict = field(default_factory=lambda: {"start": "09:00", "end": "18:00"})
    preferred_browser: str = "Chrome"
    preferred_editor: str = "VS Code"
    preferred_music_app: str = "YouTube Music"
    communication_style: str = "casual"
    key_contacts: dict[str, str] = field(default_factory=dict)
    github_username: str = ""

    # ── Rich personality / deep personal data (set during onboarding) ──────
    # Skills & expertise
    skills: list[str] = field(default_factory=list)
    # Daily routine
    daily_routine: str = ""
    # Goals & aspirations
    goals: list[str] = field(default_factory=list)
    # Learning interests
    learning_interests: list[str] = field(default_factory=list)
    # Tech stack / dev tools
    tech_stack: str = ""
    # Music taste
    music_taste: str = ""
    # News / content interests
    content_interests: str = ""
    # Personal quirks / habits
    personal_notes: str = ""
    # Work style
    work_style: str = ""

    # Auto-learned preferences
    _learned: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str = PROFILE_PATH) -> "UserProfile":
        """Load profile from disk, or create default."""
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                profile = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
                profile._learned = data.get("_learned", {})
                return profile
            except Exception as e:
                print(f"[Profile] Error loading profile: {e}, using defaults.")
        return cls()

    def save(self, path: str = PROFILE_PATH) -> None:
        """Persist profile to disk."""
        data = asdict(self)
        data["_learned"] = self._learned
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Profile] Error saving profile: {e}")

    def learn(self, key: str, value: Any) -> None:
        """Auto-learn a preference from user behavior."""
        self._learned[key] = value
        self.save()

    def get_learned(self, key: str, default: Any = None) -> Any:
        return self._learned.get(key, default)

    def resolve_contact(self, name: str) -> str | None:
        """Resolve a person's name to their email. e.g. 'email Rahul' → name@example.com"""
        name_lower = name.lower().strip()
        # Direct match
        if name_lower in self.key_contacts:
            return self.key_contacts[name_lower]
        # Partial match
        for k, v in self.key_contacts.items():
            if k in name_lower or name_lower in k:
                return v
        return None

    def build_profile_block(self) -> str:
        """Build USER PROFILE block for agent system prompts."""
        style_map = {
            "casual": "Warm, witty, concise. Use 'sir' occasionally.",
            "formal": "Professional, respectful, structured.",
            "terse": "Ultra-brief, 1 sentence max. No pleasantries.",
        }
        style_desc = style_map.get(self.communication_style, style_map["casual"])

        lines = [
            f"USER PROFILE:",
            f"  Name: {self.name}",
            f"  Timezone: {self.timezone}",
            f"  Work hours: {self.work_hours['start']}–{self.work_hours['end']}",
            f"  Preferred browser: {self.preferred_browser}",
            f"  Preferred editor: {self.preferred_editor}",
            f"  Preferred music: {self.preferred_music_app}",
            f"  Communication: {style_desc}",
        ]
        if self.github_username:
            lines.append(f"  GitHub: {self.github_username}")

        if self.key_contacts:
            lines.append("  Key contacts:")
            for name, email in self.key_contacts.items():
                lines.append(f"    {name} → {email}")

        # ── Rich personality ────────────────────────────────────────────
        if self.skills:
            lines.append(f"  Skills: {', '.join(self.skills)}")
        if self.daily_routine:
            lines.append(f"  Daily routine: {self.daily_routine}")
        if self.goals:
            lines.append(f"  Goals: {', '.join(self.goals)}")
        if self.learning_interests:
            lines.append(f"  Learning interests: {', '.join(self.learning_interests)}")
        if self.tech_stack:
            lines.append(f"  Tech stack: {self.tech_stack}")
        if self.music_taste:
            lines.append(f"  Music taste: {self.music_taste}")
        if self.content_interests:
            lines.append(f"  Content interests: {self.content_interests}")
        if self.personal_notes:
            lines.append(f"  Personal notes: {self.personal_notes}")
        if self.work_style:
            lines.append(f"  Work style: {self.work_style}")

        # Include learned preferences
        if self._learned:
            lines.append("  Learned preferences:")
            for k, v in self._learned.items():
                lines.append(f"    {k}: {v}")

        return "\n\n" + "\n".join(lines)

    def __repr__(self) -> str:
        return f"UserProfile(name='{self.name}', style='{self.communication_style}')"
