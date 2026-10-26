"""Load repository-owned template processors; never guess unsupported capabilities."""
import importlib.util
from pathlib import Path
import re


def load_processor(scene, filename="bcut.py"):
    name = scene["episode"].get("template", "official")
    if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        raise ValueError("Invalid template name")
    root = Path(__file__).resolve().parents[1] / "templates"
    path = root / name / filename
    if not path.is_file():
        raise ValueError(f"Template {name} has no {filename} processor")
    spec = importlib.util.spec_from_file_location(f"bcut_{name}_{path.stem}", path)
    processor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(processor)
    return processor
