"""Screen vision — GPT-4.1-mini powered screenshot analysis."""

import base64
import json
import os
import re
import subprocess
import tempfile
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import openai


_MODEL = "gpt-4.1"


def _get_client() -> openai.OpenAI:
    """Return OpenAI client."""
    return openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


def _take_screenshot() -> str:
    """Take a screenshot, return file path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    subprocess.run(["screencapture", "-x", tmp.name], capture_output=True)
    return tmp.name


def _resize_for_api(path: str) -> str:
    """Downscale Retina screenshot to ~1440px wide for faster API calls."""
    try:
        from PIL import Image

        img = Image.open(path)
        w, h = img.size
        if w > 2000:
            new_w, new_h = w // 2, h // 2
            img_small = img.resize((new_w, new_h), Image.LANCZOS)
            small_path = path + "_small.png"
            img_small.save(small_path, optimize=True)
            return small_path
    except ImportError:
        pass
    return path


def _base64_image(path: str) -> str:
    """Read image and return base64 string."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response (handles markdown wrapping)."""
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    m = re.search(r'```(?:json)?\s*\n?({.*?})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _cleanup(*paths: str) -> None:
    """Remove temp files silently."""
    for p in paths:
        try:
            os.unlink(p)
        except Exception:
            pass


def find_element_on_screen(target: str, min_y: int = 0) -> dict:
    """Find a UI element on screen via GPT Vision.

    Returns {"found": True, "x": int, "y": int} or {"found": False, "error": str}.
    Coordinates are logical (non-retina) pixels.
    """
    screenshot_path = _take_screenshot()
    small_path = _resize_for_api(screenshot_path)
    cleanup_paths = [screenshot_path]
    if small_path != screenshot_path:
        cleanup_paths.append(small_path)

    try:
        b64 = _base64_image(small_path)

        try:
            from PIL import Image

            img = Image.open(small_path)
            img_w, img_h = img.size
        except ImportError:
            img_w, img_h = 1440, 900

        prompt = (
            f"This is a screenshot ({img_w}x{img_h} pixels). "
            f"Find the clickable UI element that best matches: '{target}'\n\n"
            f"Rules:\n"
            f"- Return the EXACT center pixel of the button/icon/element itself — not the text label next to it\n"
            f"- For a play button (triangle icon): return the center of the triangle, not nearby text\n"
            f"- For a button with text: return the center of the button background, not the edge\n"
            f"- Be precise — even 20px off can click the wrong thing\n\n"
            f"Return ONLY this JSON (no explanation, no markdown):\n"
            f'{{"x": <integer>, "y": <integer>}}\n'
            f'If the element is not visible, return: {{"found": false}}'
        )

        client = _get_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{b64}", "detail": "high",
                    }},
                ],
            }],
            max_tokens=100,
            temperature=0.1,
        )

        text = response.choices[0].message.content or ""
        print(f"[Vision] GPT response: {text[:120]}", flush=True)
        result = _extract_json(text)

        if result and result.get("x") is not None and result.get("y") is not None:
            x, y = int(result["x"]), int(result["y"])
            if y >= min_y:
                return {"found": True, "x": x, "y": y, "source": "gpt_vision"}

        return {"found": False, "error": f"Could not locate '{target}' on screen"}

    except Exception as e:
        print(f"[Vision] Error: {e}", flush=True)
        return {"found": False, "error": f"Vision error: {e}"}
    finally:
        _cleanup(*cleanup_paths)


def describe_screen() -> str:
    """Describe what's currently visible on screen."""
    screenshot_path = _take_screenshot()
    small_path = _resize_for_api(screenshot_path)
    cleanup_paths = [screenshot_path]
    if small_path != screenshot_path:
        cleanup_paths.append(small_path)

    try:
        b64 = _base64_image(small_path)
        client = _get_client()

        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "Describe what you see on this screenshot. "
                        "List visible apps, windows, buttons, and key text. "
                        "Be concise — 3-5 sentences max."
                    )},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{b64}", "detail": "high",
                    }},
                ],
            }],
            max_tokens=256,
            temperature=0.3,
        )

        return response.choices[0].message.content or "Could not describe screen."

    except Exception as e:
        return f"Error describing screen: {e}"
    finally:
        _cleanup(*cleanup_paths)


def read_document_from_screen() -> str:
    """Extract text from a document/PDF visible on screen via GPT Vision."""
    screenshot_path = _take_screenshot()
    small_path = _resize_for_api(screenshot_path)
    cleanup_paths = [screenshot_path]
    if small_path != screenshot_path:
        cleanup_paths.append(small_path)

    try:
        b64 = _base64_image(small_path)
        client = _get_client()

        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "Extract ALL text from this document/screenshot. "
                        "Preserve structure (headings, paragraphs, lists). "
                        "Return the text exactly as it appears."
                    )},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{b64}", "detail": "high",
                    }},
                ],
            }],
            max_tokens=1024,
            temperature=0.1,
        )

        return response.choices[0].message.content or "No text found."

    except Exception as e:
        return f"Error reading document: {e}"
    finally:
        _cleanup(*cleanup_paths)
