from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from depthflow_api.tts import WordBoundary


MAX_CUE_CHARS = 80
MAX_CUE_WORDS = 14
CUE_TAIL_PADDING_SECONDS = 0.15
SENTENCE_ENDINGS = frozenset(".!?:;")
PUNCTUATION_TOKENS = frozenset(".,!?:;")


@dataclass(frozen=True)
class SubtitleCue:
    start: float
    end: float
    text: str


def write_srt(boundaries: list[WordBoundary], path: Path) -> Path:
    cues = _build_sentence_cues(boundaries)
    if not cues:
        if path.exists():
            path.unlink()
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_format_srt(cues), encoding="utf-8")
    return path


def _build_sentence_cues(boundaries: list[WordBoundary]) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    words: list[str] = []
    cue_start: float | None = None
    cue_end = 0.0
    word_count = 0

    for boundary in boundaries:
        text = boundary.text.strip()
        if not text:
            continue

        if _is_punctuation_token(text):
            if not words:
                continue
            words[-1] = f"{words[-1]}{text}"
        else:
            if words and _would_exceed_cue_limits(words, text, word_count):
                cues.append(SubtitleCue(cue_start, cue_end, " ".join(words)))
                words = []
                cue_start = boundary.start
                cue_end = 0.0
                word_count = 0

            if cue_start is None:
                cue_start = boundary.start
            words.append(text)
            word_count += 1

        cue_end = max(cue_end, boundary.start + max(boundary.duration, 0.0))
        if boundary.is_sentence_end or text[-1] in SENTENCE_ENDINGS:
            cues.append(SubtitleCue(cue_start, cue_end, " ".join(words)))
            words = []
            cue_start = None
            cue_end = 0.0
            word_count = 0

    if words and cue_start is not None:
        cues.append(SubtitleCue(cue_start, cue_end, " ".join(words)))

    return _pad_and_clamp_cues(cues)


def _would_exceed_cue_limits(words: list[str], next_word: str, word_count: int) -> bool:
    next_text = " ".join([*words, next_word])
    return len(next_text) > MAX_CUE_CHARS or word_count + 1 > MAX_CUE_WORDS


def _pad_and_clamp_cues(cues: list[SubtitleCue]) -> list[SubtitleCue]:
    padded: list[SubtitleCue] = []
    for index, cue in enumerate(cues):
        next_start = cues[index + 1].start if index + 1 < len(cues) else None
        end = cue.end + CUE_TAIL_PADDING_SECONDS
        if next_start is not None:
            end = min(end, next_start)
        end = max(end, cue.start + 0.001)
        padded.append(SubtitleCue(cue.start, end, cue.text))
    return padded


def _format_srt(cues: list[SubtitleCue]) -> str:
    blocks = [
        f"{index}\n{_format_timestamp(cue.start)} --> {_format_timestamp(cue.end)}\n{cue.text}"
        for index, cue in enumerate(cues, start=1)
    ]
    return "\n\n".join(blocks) + "\n"


def _format_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _is_punctuation_token(text: str) -> bool:
    return bool(text) and all(character in PUNCTUATION_TOKENS for character in text)
