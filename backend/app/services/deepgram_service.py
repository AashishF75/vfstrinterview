import logging
from typing import Tuple, Optional
import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

# Permitted audio content types for transcription
ALLOWED_AUDIO_MIME_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mp3",
    "audio/mpeg",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/ogg",
    "audio/opus",
    "application/octet-stream",  # Fallback from some mobile browsers
}


class DeepgramService:
    """
    Backend service for Deepgram Speech-to-Text (Listen API) and Text-to-Speech (Speak API).

    Security & Privacy Safeguards:
    - Deepgram API key remains strictly server-side and is never exposed to clients.
    - Raw audio bytes and sensitive transcripts are NEVER logged to disk or console.
    - Strict timeouts, payload bounds, and HTTP status handling protect application integrity.
    - Gracefully fails with 503 Service Unavailable when the service key is not configured,
      allowing the frontend to seamlessly fallback to browser-native Web Speech capabilities.
    """

    @classmethod
    def is_configured(cls) -> bool:
        """Returns True if the backend has a non-empty Deepgram API key configured."""
        return bool(settings.DEEPGRAM_API_KEY and settings.DEEPGRAM_API_KEY.strip())

    @classmethod
    async def transcribe_audio(
        cls,
        audio_bytes: bytes,
        content_type: str = "audio/webm",
    ) -> Tuple[str, float, Optional[float]]:
        """
        Transcribes candidate audio bytes into text using Deepgram's pre-recorded Listen API.

        Returns:
            Tuple of (transcript_text, confidence_score, duration_seconds)

        Raises:
            HTTPException 503: If Deepgram is not configured.
            HTTPException 400: If audio payload is empty or invalid.
            HTTPException 413: If audio payload exceeds size limits.
            HTTPException 502/504: On upstream communication failures or timeouts.
        """
        if not cls.is_configured():
            logger.info("Deepgram transcription requested but DEEPGRAM_API_KEY is not configured.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Deepgram voice transcription is not configured on this server.",
            )

        if not audio_bytes or len(audio_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Audio recording payload is empty.",
            )

        if len(audio_bytes) > settings.DEEPGRAM_MAX_AUDIO_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Audio payload exceeds maximum permitted size of {settings.DEEPGRAM_MAX_AUDIO_SIZE_BYTES // (1024 * 1024)} MB.",
            )

        # Normalize content type (strip codec parameters if present for mime matching)
        base_mime = (content_type or "audio/webm").split(";")[0].strip().lower()
        if base_mime not in ALLOWED_AUDIO_MIME_TYPES:
            # Default to audio/webm if unrecognized
            base_mime = "audio/webm"

        api_url = (
            f"{settings.DEEPGRAM_API_BASE_URL.rstrip('/')}/v1/listen"
            f"?model={settings.DEEPGRAM_STT_MODEL}&smart_format=true&punctuate=true"
        )

        headers = {
            "Authorization": f"Token {settings.DEEPGRAM_API_KEY.strip()}",
            "Content-Type": base_mime,
        }

        try:
            async with httpx.AsyncClient(timeout=settings.DEEPGRAM_REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(api_url, headers=headers, content=audio_bytes)

            if response.status_code == 401 or response.status_code == 403:
                logger.error("Deepgram authentication error (invalid or unauthorized API token).")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Deepgram service rejected authorization credentials.",
                )

            if response.status_code != 200:
                logger.error(f"Deepgram STT responded with HTTP status {response.status_code}.")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Deepgram transcription failed with status code {response.status_code}.",
                )

            data = response.json()
            results = data.get("results", {})
            channels = results.get("channels", [])
            transcript = ""
            confidence = 1.0

            if channels and len(channels) > 0:
                alternatives = channels[0].get("alternatives", [])
                if alternatives and len(alternatives) > 0:
                    primary_alt = alternatives[0]
                    transcript = primary_alt.get("transcript", "").strip()
                    confidence = float(primary_alt.get("confidence", 1.0))

            duration = None
            metadata = data.get("metadata", {})
            if "duration" in metadata and metadata["duration"] is not None:
                try:
                    duration = float(metadata["duration"])
                except (ValueError, TypeError):
                    pass

            return transcript, confidence, duration

        except httpx.TimeoutException:
            logger.warning("Deepgram STT request timed out.")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Deepgram transcription service timed out.",
            )
        except httpx.RequestError as exc:
            logger.warning(f"Deepgram STT network connection error: {exc.__class__.__name__}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to reach Deepgram transcription service.",
            )

    @classmethod
    async def synthesize_speech(cls, text: str) -> bytes:
        """
        Synthesizes text into spoken audio (MP3) using Deepgram's Speak API.

        Returns:
            Raw audio bytes (audio/mpeg)

        Raises:
            HTTPException 503: If Deepgram is not configured.
            HTTPException 400: If text is empty or exceeds length limits.
            HTTPException 502/504: On upstream failures or timeouts.
        """
        if not cls.is_configured():
            logger.info("Deepgram speech synthesis requested but DEEPGRAM_API_KEY is not configured.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Deepgram voice synthesis is not configured on this server.",
            )

        if not text or not text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Speech synthesis text cannot be empty.",
            )

        cleaned_text = text.strip()
        if len(cleaned_text) > 2000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Speech synthesis text exceeds maximum supported length (2000 characters).",
            )

        api_url = (
            f"{settings.DEEPGRAM_API_BASE_URL.rstrip('/')}/v1/speak"
            f"?model={settings.DEEPGRAM_TTS_MODEL}"
        )

        headers = {
            "Authorization": f"Token {settings.DEEPGRAM_API_KEY.strip()}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.DEEPGRAM_REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(api_url, headers=headers, json={"text": cleaned_text})

            if response.status_code == 401 or response.status_code == 403:
                logger.error("Deepgram TTS authentication error (invalid or unauthorized API token).")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Deepgram service rejected authorization credentials.",
                )

            if response.status_code != 200:
                logger.error(f"Deepgram TTS responded with HTTP status {response.status_code}.")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Deepgram speech synthesis failed with status code {response.status_code}.",
                )

            return response.content

        except httpx.TimeoutException:
            logger.warning("Deepgram TTS request timed out.")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Deepgram speech synthesis service timed out.",
            )
        except httpx.RequestError as exc:
            logger.warning(f"Deepgram TTS network connection error: {exc.__class__.__name__}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to reach Deepgram speech synthesis service.",
            )
