"""Mouse control — click, move, find-and-click via AX tree + Vision + OCR."""

import json
import os
import re
import subprocess
import tempfile
import time


CLICLICK = "/opt/homebrew/bin/cliclick"

# ── AX Tree (instant, ~20ms) ────────────────────────────────────────────────

_AX_FRAME_RE = re.compile(r'x:([\d.]+).*?y:([\d.]+).*?w:([\d.]+).*?h:([\d.]+)')


def _ax_parse_frame(frame_val):
    """Parse AXFrame to center (x, y)."""
    if frame_val is None:
        return None, None
    m = _AX_FRAME_RE.search(str(frame_val))
    if m:
        x, y, w, h = float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))
        return int(x + w / 2), int(y + h / 2)
    return None, None


def ax_find(target: str, app_name: str = None, exact: bool = False, min_y: int = 0) -> dict:
    """Search the macOS Accessibility tree for text. ~10-50ms, no screenshot.

    Returns {found, x, y, text, role} or {found: False}.
    Works for native apps. Does NOT work for Chrome web content.
    """
    try:
        from ApplicationServices import (
            AXUIElementCreateApplication, AXUIElementCopyAttributeValue,
            kAXChildrenAttribute, kAXRoleAttribute, kAXTitleAttribute,
            kAXValueAttribute, kAXDescriptionAttribute,
        )
        from AppKit import NSWorkspace

        target_lower = target.lower().strip()

        if app_name:
            r = subprocess.run(['pgrep', '-n', app_name], capture_output=True, text=True)
            if not r.stdout.strip():
                return {"found": False, "error": f"App '{app_name}' not running"}
            pids = [int(r.stdout.strip())]
        else:
            ws = NSWorkspace.sharedWorkspace()
            front_app = ws.frontmostApplication()
            front_pid = int(front_app.processIdentifier()) if front_app else None

            finder_r = subprocess.run(['pgrep', '-n', 'Finder'], capture_output=True, text=True)
            finder_pid = int(finder_r.stdout.strip()) if finder_r.stdout.strip() else None

            all_pids = [int(a.processIdentifier()) for a in ws.runningApplications()
                        if a.activationPolicy() == 0]
            pids = []
            if front_pid:
                pids.append(front_pid)
            if finder_pid and finder_pid != front_pid:
                pids.append(finder_pid)
            for p in all_pids:
                if p not in pids:
                    pids.append(p)

        def get_attr(elem, attr):
            err, val = AXUIElementCopyAttributeValue(elem, attr, None)
            return val if err == 0 else None

        def walk(elem, depth=0, results=None, max_depth=10):
            if results is None:
                results = []
            if depth > max_depth or len(results) > 50:
                return results

            role = get_attr(elem, kAXRoleAttribute)
            title = get_attr(elem, kAXTitleAttribute)
            value = get_attr(elem, kAXValueAttribute)
            desc = get_attr(elem, kAXDescriptionAttribute)

            text = title or desc or (value if isinstance(value, str) and len(str(value)) < 300 else None)
            if text and len(str(text).strip()) > 0:
                text_str = str(text).strip()
                text_lower = text_str.lower()
                matched = (text_lower == target_lower) if exact else (target_lower in text_lower)
                if matched:
                    cx, cy = _ax_parse_frame(get_attr(elem, 'AXFrame'))
                    if cx is not None and cy >= min_y:
                        role_str = str(role) if role else ''
                        on_screen = cx > 10
                        results.append({
                            'text': text_str[:80],
                            'x': cx, 'y': cy,
                            'role': role_str,
                            'score': (2.0 if text_lower == target_lower else 1.0) * (1.0 if on_screen else 0.1),
                        })

            children = get_attr(elem, kAXChildrenAttribute)
            if children:
                for c in children:
                    walk(c, depth + 1, results, max_depth)
            return results

        deadline = time.time() + 1.5
        all_results = []
        for pid in pids:
            if time.time() > deadline:
                break
            try:
                app_elem = AXUIElementCreateApplication(pid)
                found = walk(app_elem)
                all_results.extend(found)
                if any(r['score'] >= 1.9 for r in found):
                    break
            except Exception:
                continue

        if not all_results:
            return {"found": False}

        visible = [r for r in all_results if r['x'] > 10 and r['y'] < 1100]
        if not visible:
            visible = all_results

        _ROLE_PRIORITY = {'AXImage': 3, 'AXButton': 3, 'AXStaticText': 2,
                          'AXTextField': 2, 'AXLink': 2, 'AXMenuItem': 0}

        def _sort_key(r):
            rp = _ROLE_PRIORITY.get(r['role'], 1)
            return (-r['score'], -rp, r['y'])

        best = sorted(visible, key=_sort_key)[0]
        return {"found": True, "x": best['x'], "y": best['y'],
                "text": best['text'], "role": best['role']}

    except Exception as e:
        return {"found": False, "error": str(e)}


# ── macOS Vision OCR (fallback, ~0.5s) ──────────────────────────────────────

def apple_ocr(image_path: str, target: str, min_y: int = 0, exact: bool = False) -> dict:
    """macOS native Vision framework OCR — zero dependencies."""
    try:
        script = f'''
import Cocoa
import Vision

let img = NSImage(contentsOfFile: "{image_path}")!
let cgImage = img.cgImage(forProposedRect: nil, context: nil, hints: nil)!

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try handler.perform([request])

let imgW = Double(cgImage.width)
let imgH = Double(cgImage.height)
let scale = imgW > 2000 ? 2.0 : 1.0

var results: [[String: Any]] = []
for obs in (request.results ?? []) {{
    guard let top = obs.topCandidates(1).first else {{ continue }}
    let box = obs.boundingBox
    let cx = (box.origin.x + box.width / 2) * imgW / scale
    let cy = (1.0 - box.origin.y - box.height / 2) * imgH / scale
    results.append(["text": top.string, "x": Int(cx), "y": Int(cy), "conf": top.confidence])
}}

let data = try JSONSerialization.data(withJSONObject: results)
print(String(data: data, encoding: .utf8)!)
'''
        result = subprocess.run(
            ["swift", "-e", script],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return {"error": f"Vision OCR failed: {result.stderr[:200]}"}

        detections = json.loads(result.stdout.strip())
        all_texts = [d["text"] for d in detections if d.get("text")]
        print(f"[OCR] macOS Vision detected {len(all_texts)} elements", flush=True)

        target_lower = target.lower().strip()
        best_x, best_y, best_score = None, None, -1.0

        for d in detections:
            text = d.get("text", "").strip()
            text_lower = text.lower()
            cx, cy = d.get("x", 0), d.get("y", 0)

            if cy < min_y:
                continue

            if exact:
                matched = text_lower == target_lower
            else:
                matched = target_lower in text_lower or text_lower in target_lower

            if matched:
                score = (1.0 if text_lower == target_lower else 0.5) + d.get("conf", 0.5)
                if score > best_score:
                    best_score = score
                    best_x, best_y = cx, cy

        if best_x is not None:
            return {"found": True, "x": best_x, "y": best_y,
                    "confidence": best_score, "all_texts": all_texts[:60]}
        return {"found": False, "all_texts": all_texts[:60]}

    except Exception as e:
        return {"error": str(e)}


# ── Find and Click (3-tier: AX → GPT Vision → OCR) ──────────────────────────

def find_and_click(target: str, double: bool = False, min_y: int = 0, exact: bool = False) -> str:
    """Find text on screen and click it.

    Strategy:
    1. AX tree search — instant (~20ms), native apps
    2. GPT-4.1-mini Vision — full UI understanding (~1-2s)
    3. macOS Vision OCR — text matching fallback
    """
    # 1. AX tree
    print(f"[AX] Looking for '{target}'...", flush=True)
    ax_result = ax_find(target, exact=exact, min_y=min_y)

    if ax_result.get("found"):
        x, y = ax_result["x"], ax_result["y"]
        print(f"[AX] Found '{ax_result['text']}' at ({x},{y})", flush=True)
        click_cmd = f"dc:{x},{y}" if double else f"c:{x},{y}"
        subprocess.run([CLICLICK, click_cmd], capture_output=True)
        action_name = "Double-clicked" if double else "Clicked"
        return f"{action_name} '{target}' at ({x}, {y})."

    # 2. GPT Vision
    print(f"[AX] Not found — falling back to GPT Vision...", flush=True)
    try:
        from tools.vision import find_element_on_screen
        vision_result = find_element_on_screen(target, min_y=min_y)

        if vision_result.get("found"):
            x, y = vision_result["x"], vision_result["y"]
            print(f"[Vision] Found '{target}' at ({x},{y})", flush=True)
            click_cmd = f"dc:{x},{y}" if double else f"c:{x},{y}"
            subprocess.run([CLICLICK, click_cmd], capture_output=True)
            action_name = "Double-clicked" if double else "Clicked"
            return f"{action_name} '{target}' at ({x}, {y})."

        print(f"[Vision] Not found: {vision_result.get('error', '')}", flush=True)
    except Exception as e:
        print(f"[Vision] Error: {e}", flush=True)

    # 3. macOS OCR fallback
    print(f"[Vision] Falling back to OCR...", flush=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    time.sleep(0.15)
    subprocess.run(["screencapture", "-x", tmp_path], capture_output=True)

    try:
        data = apple_ocr(tmp_path, target, min_y=min_y, exact=exact)

        if "error" in data:
            return f"OCR error: {data['error']}"

        all_texts = data.get("all_texts", [])
        print(f"[OCR] Detected {len(all_texts)} elements", flush=True)

        if not data.get("found"):
            visible = ", ".join(t for t in all_texts if t and len(t) > 1)[:300]
            return f"Could not find '{target}' on screen. Visible text: {visible}"

        x, y = data["x"], data["y"]
        click_cmd = f"dc:{x},{y}" if double else f"c:{x},{y}"
        subprocess.run([CLICLICK, click_cmd], capture_output=True)
        action_name = "Double-clicked" if double else "Clicked"
        return f"{action_name} '{target}' at ({x}, {y})."

    except Exception as e:
        return f"Vision error: {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ── Simple mouse actions ─────────────────────────────────────────────────────

def click(x: int, y: int) -> str:
    subprocess.run([CLICLICK, f"c:{x},{y}"], capture_output=True)
    return f"Clicked at ({x},{y})."


def double_click(x: int, y: int) -> str:
    subprocess.run([CLICLICK, f"dc:{x},{y}"], capture_output=True)
    return f"Double-clicked at ({x},{y})."


def right_click(x: int, y: int) -> str:
    subprocess.run([CLICLICK, f"rc:{x},{y}"], capture_output=True)
    return f"Right-clicked at ({x},{y})."


def move(x: int, y: int) -> str:
    subprocess.run([CLICLICK, f"m:{x},{y}"], capture_output=True)
    return f"Moved mouse to ({x},{y})."


def position() -> str:
    r = subprocess.run([CLICLICK, "p"], capture_output=True, text=True)
    return f"Mouse is at {r.stdout.strip()}"
