import difflib
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


STATE_VERSION = 1
ACTION_REQUIRED = {"unreviewed", "source_changed", "translation_changed", "both_changed", "missing_source", "missing_translation"}
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


class ReviewError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewError("Cannot read {}: {}".format(path, exc))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".doc-review-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(name, str(path))
    finally:
        if os.path.exists(name):
            os.unlink(name)


def safe_relative(root, raw):
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise ReviewError("Paths must be nonempty POSIX-style paths: {!r}".format(raw))
    relative = Path(raw)
    if relative.is_absolute() or relative.drive or any(part in ("..", "") for part in relative.parts):
        raise ReviewError("Path must stay inside the repository: {!r}".format(raw))
    result = (root / relative).resolve()
    try:
        result.relative_to(root)
    except ValueError:
        raise ReviewError("Path escapes the repository: {!r}".format(raw))
    return result


def load_config(config_path):
    config_path = Path(config_path).resolve()
    root = config_path.parent
    config = read_json(config_path)
    if config.get("version") != 1 or not isinstance(config.get("pairs"), list):
        raise ReviewError("Config needs version 1 and a pairs array")
    if not config["pairs"]:
        raise ReviewError("Config has no document pairs")
    seen = set()
    pairs = []
    for pair in config["pairs"]:
        if not isinstance(pair, dict) or not isinstance(pair.get("id"), str) or not pair["id"]:
            raise ReviewError("Every pair needs a nonempty id")
        if pair["id"] in seen:
            raise ReviewError("Duplicate pair id: {}".format(pair["id"]))
        seen.add(pair["id"])
        for key in ("source", "translation"):
            safe_relative(root, pair.get(key))
        pairs.append({"id": pair["id"], "source": pair["source"], "translation": pair["translation"]})
    state_path = safe_relative(root, config.get("state", ".doc-review/state.json"))
    return root, pairs, state_path


def load_state(state_path):
    if not state_path.exists():
        return {"version": STATE_VERSION, "pairs": {}}
    state = read_json(state_path)
    if state.get("version") != STATE_VERSION or not isinstance(state.get("pairs"), dict):
        raise ReviewError("Unsupported state file: {}".format(state_path))
    return state


def file_data(root, raw):
    path = safe_relative(root, raw)
    if not path.is_file():
        return None
    try:
        data = path.read_bytes()
        content = data.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReviewError("Cannot read UTF-8 Markdown file {}: {}".format(raw, exc))
    return {"hash": digest(data), "text": content}


def status_for(source, translation, record, pair):
    if source is None:
        return "missing_source"
    if translation is None:
        return "missing_translation"
    if not record or record.get("source_path") != pair["source"] or record.get("translation_path") != pair["translation"]:
        return "unreviewed"
    source_changed = record.get("source_hash") != source["hash"]
    translation_changed = record.get("translation_hash") != translation["hash"]
    if source_changed and translation_changed:
        return "both_changed"
    if source_changed:
        return "source_changed"
    if translation_changed:
        return "translation_changed"
    return "current"


def sections(text):
    result = []
    heading = "(before first heading)"
    for line in text.splitlines():
        if line.startswith("#") and line.lstrip("#").startswith(" "):
            heading = line.strip()
        result.append((heading, line))
    return result


def changed_sections(old, new):
    old_lines = sections(old)
    new_lines = sections(new)
    matcher = difflib.SequenceMatcher(a=[line for _, line in old_lines], b=[line for _, line in new_lines], autojunk=False)
    found = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if j1 < len(new_lines):
            heading = new_lines[j1][0]
        elif i1 < len(old_lines):
            heading = old_lines[i1][0]
        else:
            heading = "(before first heading)"
        if heading not in found:
            found.append(heading)
    return found


def structural_clues(source_text, translation_text):
    """Only report mechanical clues; different translated prose is not an error."""
    source_fences = sum(bool(FENCE.match(line)) for line in source_text.splitlines())
    target_fences = sum(bool(FENCE.match(line)) for line in translation_text.splitlines())
    clues = []
    if source_fences != target_fences:
        clues.append("Code fence counts differ ({} vs {}).".format(source_fences, target_fences))
    return clues


def scan(config_path):
    root, pairs, state_path = load_config(config_path)
    state = load_state(state_path)
    results = []
    for pair in pairs:
        source = file_data(root, pair["source"])
        translation = file_data(root, pair["translation"])
        record = state["pairs"].get(pair["id"])
        status = status_for(source, translation, record, pair)
        changed = []
        source_diff = ""
        if source and record and record.get("source_text") is not None and record.get("source_hash") != source["hash"]:
            changed = changed_sections(record["source_text"], source["text"])
            source_diff = "".join(difflib.unified_diff(
                record["source_text"].splitlines(keepends=True),
                source["text"].splitlines(keepends=True),
                fromfile="last reviewed source", tofile="current source",
            ))
        results.append({
            "id": pair["id"], "source": pair["source"], "translation": pair["translation"],
            "status": status, "changed_sections": changed, "source_diff": source_diff,
            "clues": structural_clues(source["text"], translation["text"]) if source and translation else [],
            "reviewed_at": record.get("reviewed_at") if record else None,
            "reviewer": record.get("reviewer") if record else None,
            "reason": record.get("reason") if record else None,
        })
    return {"version": 1, "root": str(root), "action_required": sum(item["status"] in ACTION_REQUIRED for item in results), "pairs": results}


def acknowledge(config_path, pair_id, reviewer, reason):
    if not reviewer.strip() or not reason.strip():
        raise ReviewError("Reviewer and review reason are required")
    root, pairs, state_path = load_config(config_path)
    pair = next((item for item in pairs if item["id"] == pair_id), None)
    if pair is None:
        raise ReviewError("Unknown pair id: {}".format(pair_id))
    source = file_data(root, pair["source"])
    translation = file_data(root, pair["translation"])
    if source is None or translation is None:
        raise ReviewError("Both documents must exist before review can be recorded")
    state = load_state(state_path)
    state["pairs"][pair_id] = {
        "source_path": pair["source"], "translation_path": pair["translation"],
        "source_hash": source["hash"], "translation_hash": translation["hash"],
        "source_text": source["text"],
        "reviewer": reviewer.strip(), "reason": reason.strip(),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(state_path, state)
    return state_path


def markdown_report(report):
    lines = ["# Translation review", "", "Pairs requiring review: **{}** / {}".format(report["action_required"], len(report["pairs"])), ""]
    for item in report["pairs"]:
        lines.extend(["## {} — {}".format(item["id"], item["status"]), "", "Source: `{}`  ".format(item["source"]), "Translation: `{}`".format(item["translation"]), ""])
        if item["changed_sections"]:
            lines.append("Source sections to inspect: {}".format(", ".join("`{}`".format(x.replace("`", "")) for x in item["changed_sections"])))
            lines.append("")
        if item["source_diff"]:
            lines.extend(["```diff", item["source_diff"].rstrip(), "```", ""])
        for clue in item["clues"]:
            lines.append("- Clue: {}".format(clue))
        if item["clues"]:
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
