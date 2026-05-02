from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from depthflow_api.env import load_env_file


DEFAULT_AZURE_SPEECH_VOICE = "en-US-FableTurboMultilingualNeural"
TICKS_PER_SECOND = 10_000_000


@dataclass(frozen=True)
class WordBoundary:
    text: str
    start: float
    duration: float
    is_sentence_end: bool = False


@dataclass(frozen=True)
class SpeechSynthesisResult:
    audio_path: Path
    word_boundaries: list[WordBoundary]


@dataclass(frozen=True)
class AzureTextToSpeech:
    subscription_key: str
    endpoint: str
    voice_name: str = DEFAULT_AZURE_SPEECH_VOICE

    @classmethod
    def from_env(cls) -> "AzureTextToSpeech":
        load_env_file()

        subscription_key = os.getenv("AZURE_SPEECH_KEY")
        endpoint = os.getenv("AZURE_SPEECH_ENDPOINT")
        voice_name = os.getenv("AZURE_SPEECH_VOICE") or DEFAULT_AZURE_SPEECH_VOICE

        if not subscription_key or not endpoint:
            raise RuntimeError(
                "Azure speech synthesis requires AZURE_SPEECH_KEY and AZURE_SPEECH_ENDPOINT"
            )

        return cls(
            subscription_key=subscription_key,
            endpoint=endpoint,
            voice_name=voice_name,
        )

    def synthesize_to_file(
        self,
        text: str,
        output_path: Path,
        voice_name: str | None = None,
    ) -> SpeechSynthesisResult:
        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError as exc:  # pragma: no cover - depends on deployed environment
            raise RuntimeError(
                "azure-cognitiveservices-speech is required for speech synthesis"
            ) from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        speech_config = speechsdk.SpeechConfig(
            subscription=self.subscription_key,
            endpoint=self.endpoint,
        )
        speech_config.speech_synthesis_voice_name = voice_name or self.voice_name

        audio_config = speechsdk.audio.AudioOutputConfig(filename=str(output_path))
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )
        word_boundaries: list[WordBoundary] = []

        def on_word_boundary(event: Any) -> None:
            word_boundaries.append(
                WordBoundary(
                    text=str(getattr(event, "text", "")),
                    start=_speech_ticks_to_seconds(getattr(event, "audio_offset", 0)),
                    duration=_speech_ticks_to_seconds(getattr(event, "duration", 0)),
                    is_sentence_end=_is_sentence_boundary(event, speechsdk),
                )
            )

        synthesizer.synthesis_word_boundary.connect(on_word_boundary)
        result = synthesizer.speak_text_async(text).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return SpeechSynthesisResult(
                audio_path=output_path,
                word_boundaries=word_boundaries,
            )

        details = getattr(result, "cancellation_details", None)
        if details is None:
            details = speechsdk.SpeechSynthesisCancellationDetails(result)
        message = getattr(details, "error_details", None) or str(result.reason)
        raise RuntimeError(f"Azure speech synthesis failed: {message}")


def _speech_ticks_to_seconds(value: Any) -> float:
    total_seconds = getattr(value, "total_seconds", None)
    if callable(total_seconds):
        return float(total_seconds())

    try:
        return float(value) / TICKS_PER_SECOND
    except (TypeError, ValueError):
        return 0.0


def _is_sentence_boundary(event: Any, speechsdk: Any) -> bool:
    boundary_type = getattr(event, "boundary_type", None)
    boundary_types = getattr(speechsdk, "SpeechSynthesisBoundaryType", None)
    sentence_boundary = getattr(boundary_types, "Sentence", None)
    if sentence_boundary is not None and boundary_type == sentence_boundary:
        return True

    boundary_name = getattr(boundary_type, "name", None)
    if isinstance(boundary_name, str):
        return boundary_name.lower() == "sentence"
    return str(boundary_type).lower().endswith("sentence")
