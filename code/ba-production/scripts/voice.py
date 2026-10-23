#!/usr/bin/env python3
"""Dedicated voice generation CLI for BA short-drama episodes.

Providers are bound per character profile (`voice.provider`):
vocu (default), fish-audio, edge-tts. API keys come from `local/.env`.

Examples:
    python scripts/voice.py check
    python scripts/voice.py sample --character saiba-momoi --text "老师，早上好。"
    python scripts/voice.py episode --episode 003-game-dev-sneak --only L7,L12
    python scripts/voice.py episode --episode 003-game-dev-sneak --fallback
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

import edge_tts
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

log = logging.getLogger("voice")
DEFAULT_LOG = lib.ROOT / "local" / "logs" / "voice.log"

FISH_URL = "https://api.fish.audio/v1/tts"
# 悟声 (Wusound) API. The public docs live at dev.wusound.cn; the API host is
# v1.wusound.cn. The older vocu.ai / voc.ink hosts either reject valid keys or
# close TTS connections, so keep this in sync with the developer docs.
# POST /tts/simple-generate returns JSON metadata with a signed `audio` URL; the
# audio itself is fetched separately from the CDN (same flow as Momoi's adapter).
VOCU_SYNC_URL = "https://v1.wusound.cn/api/tts/simple-generate"
VOCU_ASYNC_URL = "https://v1.wusound.cn/api/tts/generate"
VOCU_API = "https://v1.wusound.cn/api"


def setup_logging(path: str | None) -> Path | None:
    """Append timestamped events to one log file; console output stays unchanged."""
    if not path:
        return None
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(target, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.handlers.clear()
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    log.info("=== voice.py %s ===", " ".join(sys.argv[1:]))
    return target


# ── providers ───────────────────────────────────────────────────────────────


def synth_edge(text: str, voice: dict, out: Path, timeout: int) -> None:
    async def run() -> None:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice["voice_id"],
            rate=lib.voice_rate(voice.get("speed", 1.0)),
            pitch=voice.get("pitch", "+0Hz"),
        )
        await asyncio.wait_for(communicate.save(str(out)), timeout=timeout)

    asyncio.run(run())


def synth_fish(text: str, voice: dict, out: Path, timeout: int) -> None:
    key_env = voice.get("api_key_env") or "FISH_AUDIO_API_KEY"
    key = lib.env_value(key_env)
    if not key:
        raise RuntimeError(f"缺少 {key_env}（写入 local/.env，不要提交）")

    payload = {
        "text": text,
        "reference_id": voice["voice_id"],
        "format": voice.get("format", "mp3"),
        "mp3_bitrate": 128,
        "sample_rate": 44100,
        "normalize": True,
        "chunk_length": 200,
        "latency": "normal",
        "prosody": {
            "speed": float(voice.get("speed", 1.0)),
            "normalize_loudness": True,
        },
    }
    body, content_type = _fetch(
        "POST",
        FISH_URL,
        timeout,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "model": voice.get("model", "s2.1-pro-free"),
        },
    )
    if "audio" not in content_type or not body:
        raise RuntimeError(f"Fish Audio 返回了非音频内容（{content_type}）：{body[:200]!r}")
    out.write_bytes(body)


def vocu_sync_synthesize(text: str, voice: dict, key: str, timeout: int) -> bytes:
    """One-line sync synthesis: POST metadata, then download the signed audio URL."""
    payload = {
        "voiceId": voice["voice_id"],
        "text": text,
        "promptId": voice.get("prompt_id", "default"),
        "preset": voice.get("preset", "balance"),
        "speechRate": float(voice.get("speed", 1.0)),
        "language": voice.get("language", "auto"),
        "flash": bool(voice.get("flash", False)),
        "vivid": bool(voice.get("vivid", False)),
        "stream": False,
        "srt": False,
    }
    body, _ = _fetch(
        "POST",
        VOCU_SYNC_URL,
        timeout,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    result = json.loads(body)
    data = result.get("data") or {}
    audio_url = data.get("audio")
    if not audio_url:
        raise RuntimeError(f"Vocu returned no audio URL: {body[:300]!r}")
    log.info("vocu sync ready credit=%s url_host=%s", data.get("credit_used"), urllib.parse.urlsplit(audio_url).hostname)
    # Signed CDN URL: never forward the API key to it.
    return fetch_audio(audio_url, timeout)


def synth_vocu(text: str, voice: dict, out: Path, timeout: int) -> None:
    key = _vocu_key(voice)
    if voice.get("format", "mp3") != "mp3":
        raise ValueError("Vocu direct synthesis supports mp3 only")
    out.write_bytes(vocu_sync_synthesize(text, voice, key, timeout))


def _fetch(
    method: str, url: str, timeout: int, *, headers: dict | None = None, data: bytes | None = None
) -> tuple[bytes, str]:
    """Return (body, content-type); surface API and connection errors with context."""
    started = time.time()
    endpoint = url.split("?")[0]
    try:
        response = requests.request(method, url, headers=headers, data=data, timeout=timeout)
    except requests.RequestException as exc:
        log.warning("http %s %s failed after %.2fs: %s", method, endpoint, time.time() - started, exc)
        raise RuntimeError(f"连接失败（{endpoint}）：{exc}") from exc
    if not response.ok:
        detail = response.content[:300].decode("utf-8", "replace")
        log.warning("http %s %s HTTP %s after %.2fs: %s", method, endpoint, response.status_code, time.time() - started, detail)
        raise RuntimeError(f"HTTP {response.status_code} {response.reason}: {detail}")
    body = response.content
    log.info("http %s %s elapsed=%.2fs bytes=%d", method, endpoint, time.time() - started, len(body))
    return body, response.headers.get("content-type", "")


# ── async multi-line synthesis (悟声) ────────────────────────────────────────


def _vocu_key(voice: dict) -> str:
    key_env = voice.get("api_key_env") or "VOCU_API_KEY"
    key = lib.env_value(key_env)
    if not key:
        raise RuntimeError(f"Missing {key_env}; configure it in local/.env")
    return key


def vocu_voice_info(voice_id: str, key: str, timeout: int = 30) -> dict | None:
    """Return the voice metadata, or None when the account cannot use this voice."""
    url = f"{VOCU_API}/voice/{urllib.parse.quote(voice_id, safe=':')}"
    try:
        body, _ = _fetch("GET", url, timeout, headers={"Authorization": f"Bearer {key}"})
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise
    return json.loads(body).get("data")


def vocu_async_synthesize(
    contents: list[dict], key: str, timeout: int, poll_interval: float = 4.0
) -> list[dict]:
    """Submit one multi-line async task and poll until it finishes.

    Returns the per-item metadata (with `audio` URLs) in request order.
    """
    payload = json.dumps({"contents": contents}, ensure_ascii=False).encode("utf-8")
    body, _ = _fetch(
        "POST",
        VOCU_ASYNC_URL,
        timeout,
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    task = json.loads(body).get("data") or {}
    task_id = task.get("id")
    if not task_id:
        raise RuntimeError(f"async task creation returned no id: {body[:300]!r}")
    status = task.get("status", "pending")
    log.info("async created id=%s status=%s items=%d", task_id, status, len(contents))
    deadline = time.time() + timeout
    while status not in ("generated", "failed"):
        if time.time() > deadline:
            raise RuntimeError(f"async task {task_id} timed out after {timeout}s (status={status})")
        time.sleep(poll_interval)
        body, _ = _fetch("GET", f"{VOCU_ASYNC_URL}/{task_id}", timeout, headers={"Authorization": f"Bearer {key}"})
        task = json.loads(body).get("data") or {}
        new_status = task.get("status", status)
        if new_status != status:
            log.info("async id=%s status=%s", task_id, new_status)
        status = new_status
    if status == "failed":
        raise RuntimeError(f"async task {task_id} failed: {json.dumps(task, ensure_ascii=False)[:400]}")
    items = ((task.get("metadata") or {}).get("contents")) or []
    log.info("async done id=%s items=%d", task_id, len(items))
    if len(items) != len(contents):
        raise RuntimeError(f"async task {task_id} returned {len(items)} items, expected {len(contents)}")
    return items


def _is_audio(body: bytes, content_type: str) -> bool:
    return bool(body) and "html" not in content_type and body.lstrip()[:1] != b"<"


def _bot_challenge_cookie(body: bytes) -> str | None:
    """Cookie that answers an EdgeOne bot challenge page, or None if the page is not one.

    The page's script sets `__tst_status=<sum of the numbers in `var e={...}`>#`
    and `EO_Bot_Ssid=<number added in the cookie builder>`, then reloads.
    """
    text = body.decode("utf-8", "replace")
    ssid = re.search(r"EO_Bot_Ssid=.*?\(t,(\d+)\)", text)
    table = re.search(r"var e=\{(.*?)\},t=0", text)
    if not ssid or not table:
        return None
    status = sum(int(n) for n in re.findall(r"\w+:(\d+)", table.group(1)))
    return f"__tst_status={status}#; EO_Bot_Ssid={ssid.group(1)}"


def fetch_audio(url: str, timeout: int, attempts: int = 3) -> bytes:
    """GET a signed audio URL.

    The 悟声 CDN (EdgeOne) answers Python HTTP clients with a JS bot challenge
    page; solve it and retry with the cookie it would set.
    """
    headers = None
    for attempt in range(1, attempts + 1):
        if attempt > 2:
            time.sleep(3 * attempt)
        body, content_type = _fetch("GET", url, timeout, headers=headers)
        if _is_audio(body, content_type):
            return body
        log.warning(
            "download not audio attempt=%d/%d type=%s bytes=%d", attempt, attempts, content_type, len(body)
        )
        cookie = _bot_challenge_cookie(body)
        if not cookie:
            break
        headers = {"Cookie": cookie}
    raise RuntimeError(f"下载到的不是音频（{content_type}，{len(body)} 字节）")


def download_audio(url: str, target: Path, timeout: int) -> int:
    body = fetch_audio(url, timeout)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".download" + target.suffix)
    tmp.write_bytes(body)
    tmp.replace(target)
    return len(body)


PROVIDERS = {"fish-audio": synth_fish, "edge-tts": synth_edge, "vocu": synth_vocu}


def synth_voice(text: str, voice: dict, out: Path, timeout: int) -> None:
    provider = voice.get("provider", "")
    if provider not in PROVIDERS:
        raise RuntimeError(f"Unknown voice provider: {provider!r}")
    PROVIDERS[provider](text, voice, out, timeout)


def synth_with_retry(
    text: str, voice: dict, out: Path, timeout: int, allow_fallback: bool
) -> dict:
    """Synthesize one line, retrying three times, then the profile fallback if allowed."""
    provider = voice.get("provider", "")
    used = {
        "provider": provider,
        "voice_id": voice.get("voice_id", ""),
        "model": voice.get("model", ""),
        "speed": voice.get("speed", 1.0),
        "pitch": voice.get("pitch", ""),
        "fallback": False,
    }
    last_error: Exception | None = None
    log.info(
        "synth start provider=%s voice=%s chars=%d", provider, used["voice_id"], len(text)
    )
    for attempt in range(1, 4):
        try:
            if attempt > 1:
                time.sleep(2 ** (attempt - 1))
            synth_voice(text, voice, out, timeout)
            log.info("synth ok provider=%s attempt=%d", provider, attempt)
            return used
        except Exception as exc:  # noqa: BLE001 - network/API errors are expected
            last_error = exc
            log.warning("synth attempt %d/3 failed: %s", attempt, exc)
            out.unlink(missing_ok=True)

    fallback = voice.get("fallback")
    if allow_fallback and fallback:
        log.warning(
            "synth fallback provider=%s reason=%s", fallback.get("provider"), last_error
        )
        print(f"  WARN {provider} 合成失败，改用 fallback {fallback.get('provider')}：{last_error}")
        for attempt in range(1, 4):
            try:
                if attempt > 1:
                    time.sleep(2 ** (attempt - 1))
                synth_voice(text, fallback, out, timeout)
                log.info("synth ok provider=%s fallback=true attempt=%d", fallback.get("provider"), attempt)
                return {
                    **used,
                    "provider": fallback.get("provider", ""),
                    "voice_id": fallback.get("voice_id", ""),
                    "model": fallback.get("model", ""),
                    "speed": fallback.get("speed", 1.0),
                    "pitch": fallback.get("pitch", ""),
                    "fallback": True,
                }
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                log.warning("synth fallback attempt %d/3 failed: %s", attempt, exc)
                out.unlink(missing_ok=True)
    log.error("synth failed provider=%s error=%s", provider, last_error)
    raise RuntimeError(f"语音合成失败：{text[:24]}… ({last_error})")


def trim_silence(path: Path) -> None:
    """Trim edge silence and cap overlong internal pauses.

    Vocu community voices can leave multi-second gaps at commas and periods,
    which reads as a broken delivery in a 3-minute sketch. Edge silence is
    removed entirely; internal pauses longer than 0.6s are shortened to 0.28s
    so the beat stays without stalling.
    """
    tmp = path.with_suffix(".trim.mp3")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-af",
            "silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB,"
            "areverse,"
            "silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB,"
            "areverse,"
            "silenceremove=stop_periods=-1:stop_duration=0.6:stop_threshold=-40dB:stop_silence=0.28",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "96k",
            str(tmp),
        ],
        check=True,
    )
    tmp.replace(path)


def synthesize_line(
    text: str, voice: dict, target: Path, timeout: int, allow_fallback: bool
) -> dict:
    """Synthesize and trim one line into `target`; return the TTS metadata."""
    started = time.time()
    tts = synth_with_retry(text, voice, target, timeout, allow_fallback)
    trim_silence(target)
    seconds = lib.probe_duration(target)
    log.info(
        "line ok file=%s provider=%s fallback=%s bytes=%d duration=%.2fs wall=%.1fs",
        target.name,
        tts["provider"],
        tts["fallback"],
        target.stat().st_size,
        seconds,
        time.time() - started,
    )
    return tts


# ── episode plan ────────────────────────────────────────────────────────────


def outfit_for_line(entry: dict, board: list[dict]) -> str:
    """A line uses the outfit declared on its speaker in the owning shot."""
    lid = entry["id"]
    for shot in board:
        if lid not in (shot.get("lines") or []):
            continue
        for char in shot.get("characters") or []:
            if char.get("id") == entry["speaker"] and char.get("outfit"):
                return char["outfit"]
        break
    return ""


def load_episode_plan(episode: Path) -> tuple[dict, list[dict], dict[str, dict], dict[str, str]]:
    config = lib.load_json(episode / "episode.yaml")
    script = lib.normalize_script(lib.load_json(episode / "script.json"))
    board = lib.load_json(episode / "storyboard.json").get("shots", [])
    if not script:
        raise SystemExit("script.json 为空，先写台词再生成语音")
    character_ids = list(config.get("characters") or [])
    if not character_ids:
        raise SystemExit("episode.yaml 的 characters 为空")
    characters: dict[str, dict] = {}
    for cid in character_ids:
        characters[cid] = lib.read_character(cid)
    for line in script:
        if line["speaker"] not in characters:
            raise SystemExit(f"台词 {line['id']} 的说话人 {line['speaker']!r} 不在 episode.characters 中")
    line_outfits: dict[str, str] = {}
    for line in script:
        outfit = outfit_for_line(line, board) or characters[line["speaker"]]["default_outfit"]
        if outfit not in characters[line["speaker"]]["outfits"]:
            raise SystemExit(f"台词 {line['id']} 引用了不存在的服装 {outfit!r}")
        line_outfits[line["id"]] = outfit
    return config, script, characters, line_outfits


# ── commands ────────────────────────────────────────────────────────────────


def cmd_check(args: argparse.Namespace) -> int:
    cids = [args.character] if args.character else [
        path.parent.name for path in sorted(lib.CHARACTERS.glob("*/profile.yaml"))
    ]
    failures = 0
    for cid in cids:
        char = lib.read_character(cid)
        voice = char["voice"]
        provider = voice.get("provider", "")
        key_env = voice.get("api_key_env") or {
            "vocu": "VOCU_API_KEY",
            "fish-audio": "FISH_AUDIO_API_KEY",
        }.get(provider, "")
        has_key = bool(lib.env_value(key_env)) if key_env else None
        print(f"{cid}: provider={provider} voice={voice.get('voice_id', '')}")
        print(f"  key {key_env or '(none)'}: {'present' if has_key else 'MISSING' if has_key is not None else 'n/a'}")
        log.info("check %s provider=%s voice=%s key=%s", cid, provider, voice.get("voice_id", ""), bool(has_key))
        if args.config_only:
            continue
        # 音色存在性查询是轻量 GET（毫秒级），默认只做这一步；试音会占用生成队列，需显式 --synthesize。
        if provider == "vocu" and has_key:
            started = time.time()
            try:
                info = vocu_voice_info(voice.get("voice_id", ""), _vocu_key(voice), args.voice_check_timeout)
                elapsed = time.time() - started
                if info is None:
                    failures += 1
                    log.error("check voice invalid %s id=%s", cid, voice.get("voice_id", ""))
                    print(f"  FAIL voice {voice.get('voice_id', '')} not found ({elapsed:.1f}s)")
                else:
                    name = info.get("name") or info.get("title") or info.get("voiceName") or "(unnamed)"
                    log.info("check voice ok %s name=%s wall=%.1fs", cid, name, elapsed)
                    print(f"  voice OK {name} ({elapsed:.1f}s)")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                log.error("check voice lookup fail %s error=%s", cid, exc)
                print(f"  FAIL {exc}")
        if not args.synthesize:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "check.mp3"
            started = time.time()
            try:
                print("  synthesizing sample (may queue server-side) ...")
                synth_voice(args.text, voice, out, args.timeout)
                seconds = lib.probe_duration(out)
                log.info("check ok %s duration=%.2fs wall=%.1fs bytes=%d", cid, seconds, time.time() - started, out.stat().st_size)
                print(f"  OK {seconds:.2f}s audio, {time.time() - started:.1f}s wall, {out.stat().st_size} bytes")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                log.error("check fail %s error=%s", cid, exc)
                print(f"  FAIL {exc}")
    return 1 if failures else 0


def cmd_sample(args: argparse.Namespace) -> int:
    char = lib.read_character(args.character)
    if args.out:
        out = Path(args.out).expanduser()
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = lib.ROOT / "local" / "work" / "voice-samples" / f"{args.character}-{stamp}.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    log.info("sample character=%s chars=%d out=%s", args.character, len(args.text), out)
    tts = synthesize_line(args.text, char["voice"], out, args.timeout, args.fallback)
    seconds = lib.probe_duration(out)
    log.info("sample ok path=%s duration=%.2fs provider=%s fallback=%s", out, seconds, tts["provider"], tts["fallback"])
    print(f"{out}")
    print(f"  {seconds:.2f}s  provider={tts['provider']} fallback={tts['fallback']}")
    return 0


def cmd_episode(args: argparse.Namespace) -> int:
    episode = lib.resolve_episode(args.episode, lock=True)
    _, script, characters, line_outfits = load_episode_plan(episode)
    audio_dir = episode / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    only = {item.strip() for item in args.only.split(",") if item.strip()} if args.only else None
    if only:
        missing = only - {line["id"] for line in script}
        if missing:
            raise SystemExit(f"script.json 中没有这些台词：{', '.join(sorted(missing))}")
    selected_ids = {line["id"] for line in script if only is None or line["id"] in only}
    log.info(
        "episode start id=%s selected=%d total=%d only=%s reuse=%s fallback=%s",
        episode.name, len(selected_ids), len(script), args.only or "-", args.reuse, args.fallback,
    )

    providers: dict[str, int] = {}
    reused = 0
    failures: list[tuple[str, str]] = []
    pending: list[tuple[int, dict, dict, Path]] = []
    for index, line in enumerate(script):
        if line["id"] not in selected_ids:
            continue
        char = characters[line["speaker"]]
        target = audio_dir / f"{index:03}.mp3"
        if args.reuse and target.is_file():
            providers["reused"] = providers.get("reused", 0) + 1
            reused += 1
            continue
        if args.dry_run:
            print(f"  would synthesize {line['id']} {line['speaker']} -> {target.name}")
            continue
        pending.append((index, line, char, target))

    providers_used = {characters[line["speaker"]]["voice"].get("provider", "") for _, line, _, _ in pending}
    use_async = bool(pending) and not args.sync and providers_used == {"vocu"}
    if pending and not args.sync and not use_async:
        log.warning("mixed providers %s; using synchronous generation", sorted(providers_used))

    if use_async:
        voice = pending[0][2]["voice"]
        key = _vocu_key(voice)
        invalid: dict[str, list[str]] = {}
        for vid in sorted({char["voice"]["voice_id"] for _, _, char, _ in pending}):
            if vocu_voice_info(vid, key) is None:
                invalid[vid] = [line["id"] for _, line, char, _ in pending if char["voice"]["voice_id"] == vid]
        for vid, lids in invalid.items():
            message = f"VOICE_NOT_FOUND：{vid}（{', '.join(lids)}）"
            log.error("voice invalid %s", message)
            print(f"  FAIL {message}")
            failures.extend((lid, message) for lid in lids)
        if invalid:
            if not args.keep_going:
                return 1
            pending = [
                item for item in pending if item[2]["voice"]["voice_id"] not in invalid
            ]
        if pending:
            contents = [
                {
                    "voiceId": char["voice"]["voice_id"],
                    "text": lib.spoken_text(line),
                    "speechRate": float(char["voice"].get("speed", 1.0)),
                }
                for _, line, char, _ in pending
            ]
            log.info("async submit items=%d", len(contents))
            print(f"  异步提交 {len(contents)} 句…")
            try:
                items = vocu_async_synthesize(contents, key, args.task_timeout)
            except Exception as exc:  # noqa: BLE001
                log.error("async failed: %s", exc)
                print(f"  FAIL async: {exc}")
                if not args.fallback:
                    return 1
                log.warning("async failed; falling back to synchronous generation")
                items = []
            if items:
                for (index, line, char, target), item in zip(pending, items):
                    url = item.get("audio")
                    if not url:
                        failures.append((line["id"], f"async item has no audio: {item}"))
                        print(f"  FAIL {line['id']} {line['speaker']}: no audio URL")
                        continue
                    try:
                        size = download_audio(url, target, args.timeout)
                        trim_silence(target)
                        seconds = lib.probe_duration(target)
                    except Exception as exc:  # noqa: BLE001
                        log.error("download fail id=%s error=%s", line["id"], exc)
                        failures.append((line["id"], str(exc)))
                        print(f"  FAIL {line['id']} {line['speaker']}: {exc}")
                        continue
                    providers["vocu"] = providers.get("vocu", 0) + 1
                    log.info("line ok file=%s provider=vocu bytes=%d duration=%.2fs", target.name, size, seconds)
                    print(f"  {line['id']} {line['speaker']:14s} {'vocu':10s} {seconds:5.2f}s -> {target.name} (async)")
                pending = []

    for index, line, char, target in pending:
        try:
            tts = synthesize_line(lib.spoken_text(line), char["voice"], target, args.timeout, args.fallback)
        except Exception as exc:  # noqa: BLE001
            log.error("line fail id=%s speaker=%s error=%s", line["id"], line["speaker"], exc)
            print(f"  FAIL {line['id']} {line['speaker']}: {exc}")
            failures.append((line["id"], str(exc)))
            if not args.keep_going:
                break
            continue
        providers[tts["provider"]] = providers.get(tts["provider"], 0) + 1
        print(
            f"  {line['id']} {line['speaker']:14s} {tts['provider']:10s} "
            f"{lib.probe_duration(target):5.2f}s -> {target.name}"
            + (" (fallback)" if tts["fallback"] else "")
        )

    done = sum(providers.values())
    log.info("episode summary done=%d reused=%d failures=%d providers=%s", done, reused, len(failures), providers)
    print(f"语音：{done} 句" + (f"，复用 {reused}" if reused else "") +
          (f"，失败 {len(failures)}" if failures else ""))
    if providers:
        print("  " + ", ".join(f"{key}×{value}" for key, value in sorted(providers.items())))
    if failures:
        print("失败明细：")
        for lid, error in failures:
            print(f"  {lid}: {error}")
        return 1
    if not args.reuse and not args.dry_run:
        print("接着运行 prepare --reuse-audio 重建时间轴。")
    return 0


def cmd_retrim(args: argparse.Namespace) -> int:
    episode = lib.resolve_episode(args.episode, lock=True)
    audio_dir = episode / "audio"
    files = sorted(p for p in audio_dir.glob("[0-9][0-9][0-9].mp3") if p.is_file())
    if not files:
        raise SystemExit(f"{audio_dir} 里没有 NNN.mp3，先生成语音")
    print(f"重新裁静音：{episode.name}，{len(files)} 句")
    before_total = 0.0
    after_total = 0.0
    for path in files:
        before = lib.probe_duration(path)
        trim_silence(path)
        after = lib.probe_duration(path)
        before_total += before
        after_total += after
        log.info("retrim file=%s before=%.2fs after=%.2fs", path.name, before, after)
        print(f"  {path.name} {before:6.2f}s -> {after:6.2f}s")
    print(f"语音总长 {before_total:.1f}s -> {after_total:.1f}s；接着运行 prepare --reuse-audio 重建时间轴。")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="语音生成与 provider 检查")
    sub = parser.add_subparsers(dest="command", required=True)

    def network_opts(p: argparse.ArgumentParser) -> None:
        p.add_argument("--timeout", type=int, default=360, help="单句语音超时秒数（悟声排队可能超过 330 秒）")
        p.add_argument("--fallback", action="store_true", help="主 provider 失败时使用 profile 的 fallback")
        p.add_argument("--log", default=str(DEFAULT_LOG), help=f"日志路径（默认 {DEFAULT_LOG}）")
        p.add_argument("--no-log", action="store_true", help="不写日志文件")

    check = sub.add_parser("check", help="检查配置、key 和音色是否可用（默认不合成）")
    check.add_argument("--character", help="只检查一个角色 id")
    check.add_argument("--text", default="测试。", help="试音文本（配合 --synthesize）")
    check.add_argument("--config-only", action="store_true", help="只检查配置，不联网")
    check.add_argument("--synthesize", action="store_true", help="额外合成试音；会进入服务端生成队列，可能等待数分钟")
    check.add_argument("--voice-check-timeout", type=int, default=30, help="音色查询超时秒数（默认 30）")
    network_opts(check)
    check.set_defaults(func=cmd_check)

    sample = sub.add_parser("sample", help="为一个角色生成一条试音")
    sample.add_argument("--character", required=True)
    sample.add_argument("--text", required=True)
    sample.add_argument("--out", help="输出路径；默认 local/work/voice-samples/")
    network_opts(sample)
    sample.set_defaults(func=cmd_sample)

    episode = sub.add_parser("episode", help="生成一集全部台词的语音")
    episode.add_argument("--episode", required=True, help="剧集 id 或目录路径")
    episode.add_argument("--reuse", action="store_true", help="已有 audio/NNN.mp3 就跳过")
    episode.add_argument("--only", help="只处理这些台词，逗号分隔（如 L7,L12）")
    episode.add_argument("--keep-going", action="store_true", help="单句失败后继续合成后面的台词")
    episode.add_argument("--dry-run", action="store_true", help="只打印计划，不调用 provider")
    episode.add_argument("--sync", action="store_true", help="逐句同步合成（默认用多句异步任务）")
    episode.add_argument("--task-timeout", type=int, default=1800, help="异步任务总超时秒数")
    network_opts(episode)
    episode.set_defaults(func=cmd_episode)
    retrim = sub.add_parser("retrim", help="重新裁剪整集已有音频的静音（不重新合成）")
    retrim.add_argument("--episode", required=True, help="剧集 id 或目录路径")
    retrim.set_defaults(func=cmd_retrim)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_path = setup_logging(
        None if getattr(args, "no_log", False) else getattr(args, "log", str(DEFAULT_LOG))
    )
    if log_path:
        print(f"log: {log_path}")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
