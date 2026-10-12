from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class VoiceSpeakRequest(BaseModel):
    """Request payload for synthesizing speech via Deepgram TTS."""
    text: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Interview question or feedback text to synthesize into spoken audio",
    )

    model_config = ConfigDict(from_attributes=True)


class VoiceTranscribeResponse(BaseModel):
    """Transcription response from Deepgram STT."""
    success: bool = True
    transcript: str = Field(..., description="Transcribed candidate speech")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Transcription confidence score")
    duration_seconds: Optional[float] = Field(default=None, description="Audio duration in seconds if available")

    model_config = ConfigDict(from_attributes=True)


class VoiceStatusResponse(BaseModel):
    """Status indicating whether Deepgram voice integration is configured and active."""
    configured: bool = Field(..., description="True if backend Deepgram API key is present and configured")
    stt_model: str = Field(..., description="Active speech-to-text model identifier")
    tts_model: str = Field(..., description="Active text-to-speech model identifier")

    model_config = ConfigDict(from_attributes=True)
