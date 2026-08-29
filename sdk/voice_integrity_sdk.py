"""
Voice Integrity Enterprise SDK v2.0
Python client library for integrating Voice Integrity AI detection into banking,
telecom, and enterprise auth workflows.

Supports both REST API and gRPC connections, with comprehensive methods for:
  - Real-time session monitoring
  - One-shot audio clip analysis
  - Speaker enrollment & verification
  - Privacy/compliance management
  - Alert history & audit trail access
  - Risk trend analysis

Example usage (banking integration):
    >>> from voice_integrity_sdk import VoiceIntegrityClient
    >>> client = VoiceIntegrityClient("http://voice-integrity.bank.internal:8000")
    >>>
    >>> # Analyze a recorded call segment
    >>> result = client.analyze_audio_clip("call_recording.wav", context={
    ...     "is_known_contact": False,
    ...     "transaction_keywords_detected": ["transfer", "NEFT"],
    ...     "call_origin": "voip_unknown",
    ... })
    >>> print(f"Risk: {result['aggregate']['average_risk_score']}/100")
    >>>
    >>> # Enroll a known executive's voice for future verification
    >>> client.enroll_speaker("CFO_Sharma", ["cfo_sample1.wav", "cfo_sample2.wav"])
    >>>
    >>> # Check privacy compliance
    >>> audit = client.get_privacy_audit_log()
"""

import base64
import json
import wave
import io
import hashlib
import httpx
from typing import Dict, Any, Optional, List


class VoiceIntegrityClient:
    """Enterprise SDK for the Voice Integrity AI detection platform.

    Designed for integration with:
      - Core banking systems (transaction approval workflows)
      - Contact center platforms (live call monitoring)
      - Telecom operator fraud detection
      - Enterprise communication tools (Teams, Zoom webhook integration)
    """

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)

    def close(self):
        """Close the underlying HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ----- Session Management -----

    def set_call_context(self, session_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Attach call metadata (e.g. is_known_contact, transaction_keywords_detected).

        Args:
            session_id: Active session identifier
            context: Dict with fields like:
                - is_known_contact (bool)
                - transaction_keywords_detected (list[str])
                - prior_fraud_flags (int)
                - call_origin (str): "pstn", "voip_known", "voip_unknown", etc.
                - caller_number (str): for enrollment matching
        """
        response = self.client.post(
            f"{self.base_url}/session/{session_id}/context",
            json=context
        )
        response.raise_for_status()
        return response.json()

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """Poll full risk assessment and per-layer scores for an active session.

        Returns risk score, all per-layer scores, rationale, phase analysis,
        enrollment match status, trend analysis, and session metadata.
        """
        response = self.client.get(f"{self.base_url}/api/v1/session/{session_id}/status")
        response.raise_for_status()
        return response.json()

    def get_session_timeline(self, session_id: str) -> Dict[str, Any]:
        """Get the full per-window score timeline for a session.

        Useful for plotting risk score evolution over the duration of a call.
        """
        response = self.client.get(f"{self.base_url}/api/v1/session/{session_id}/timeline")
        response.raise_for_status()
        return response.json()

    def list_active_sessions(self) -> Dict[str, Any]:
        """List all active monitoring sessions."""
        response = self.client.get(f"{self.base_url}/api/v1/sessions")
        response.raise_for_status()
        return response.json()

    def end_session(self, session_id: str) -> Dict[str, Any]:
        """Terminate a monitoring session and cleanup memory."""
        response = self.client.delete(f"{self.base_url}/api/v1/session/{session_id}")
        response.raise_for_status()
        return response.json()

    # ----- Audio Analysis -----

    def analyze_audio_clip(self, wav_file_path: str,
                           context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Analyze a pre-recorded WAV audio clip (one-shot batch analysis).

        Args:
            wav_file_path: Path to a WAV file (any sample rate, will be resampled)
            context: Optional call context metadata

        Returns:
            Full analysis including per-window breakdown, aggregate risk,
            phase analysis, enrollment match, and final verdict.
        """
        with open(wav_file_path, "rb") as f:
            files = {"file": (wav_file_path, f, "audio/wav")}
            data = {}
            if context:
                data["caller_context"] = json.dumps(context)
            response = self.client.post(
                f"{self.base_url}/api/v1/analyze-clip",
                files=files,
                data=data
            )
            response.raise_for_status()
            return response.json()

    def is_call_safe(self, session_id: str, risk_threshold: float = 65.0) -> bool:
        """Quick check: is the current call below the risk threshold?

        Designed for inline use in transaction approval workflows:
            if client.is_call_safe(session_id):
                approve_transaction()
            else:
                require_secondary_verification()
        """
        status = self.get_session_status(session_id)
        latest = status.get("latest_analysis", {})
        risk = latest.get("risk_score", 100)
        return risk < risk_threshold

    # ----- Speaker Enrollment -----

    def enroll_speaker(self, speaker_name: str, wav_file_paths: List[str],
                       speaker_id: Optional[str] = None) -> Dict[str, Any]:
        """Enroll a known speaker from one or more audio samples.

        Args:
            speaker_name: Human-readable name (e.g. "CFO_Sharma")
            wav_file_paths: List of WAV file paths for enrollment
            speaker_id: Optional custom ID (auto-generated if omitted)

        Returns:
            Enrollment confirmation with speaker_id for future reference.
        """
        audio_samples = []
        for path in wav_file_paths:
            with open(path, "rb") as f:
                audio_bytes = f.read()
            # Extract raw PCM from WAV
            try:
                with io.BytesIO(audio_bytes) as buf:
                    with wave.open(buf, "rb") as wf:
                        raw_frames = wf.readframes(wf.getnframes())
                pcm_b64 = base64.b64encode(raw_frames).decode()
            except Exception:
                pcm_b64 = base64.b64encode(audio_bytes).decode()

            audio_samples.append({
                "pcm_base64": pcm_b64,
                "sample_rate": 16000,
            })

        payload = {
            "speaker_name": speaker_name,
            "audio_samples": audio_samples,
        }
        if speaker_id:
            payload["speaker_id"] = speaker_id

        response = self.client.post(
            f"{self.base_url}/api/v1/enroll-speaker",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    def list_enrolled_speakers(self) -> Dict[str, Any]:
        """List all enrolled speaker profiles."""
        response = self.client.get(f"{self.base_url}/api/v1/enrolled-speakers")
        response.raise_for_status()
        return response.json()

    def delete_enrolled_speaker(self, speaker_id: str) -> Dict[str, Any]:
        """Remove an enrolled speaker profile."""
        response = self.client.delete(f"{self.base_url}/api/v1/enrolled-speaker/{speaker_id}")
        response.raise_for_status()
        return response.json()

    # ----- Privacy & Compliance -----

    def get_retention_policy(self) -> Dict[str, Any]:
        """Get the current data retention policy configuration."""
        response = self.client.get(f"{self.base_url}/api/v1/privacy/retention-policy")
        response.raise_for_status()
        return response.json()

    def update_retention_policy(self, policy: Dict[str, Any]) -> Dict[str, Any]:
        """Update data retention policy settings."""
        response = self.client.put(
            f"{self.base_url}/api/v1/privacy/retention-policy",
            json=policy
        )
        response.raise_for_status()
        return response.json()

    def record_consent(self, caller_number: str, consent_type: str = "voice_analysis",
                       granted: bool = True) -> Dict[str, Any]:
        """Record user consent for voice processing (GDPR/DPDPA compliance).

        Args:
            caller_number: Raw phone number (will be hashed before sending)
            consent_type: "voice_analysis", "enrollment", or "recording"
            granted: Whether consent was granted
        """
        caller_hash = hashlib.sha256(caller_number.encode()).hexdigest()
        response = self.client.post(
            f"{self.base_url}/api/v1/privacy/consent",
            json={
                "caller_id_hash": caller_hash,
                "consent_type": consent_type,
                "granted": granted,
            }
        )
        response.raise_for_status()
        return response.json()

    def request_data_deletion(self, caller_number: str) -> Dict[str, Any]:
        """Right-to-erasure: delete all data for a caller (GDPR Art 17 / DPDPA)."""
        caller_hash = hashlib.sha256(caller_number.encode()).hexdigest()
        response = self.client.delete(f"{self.base_url}/api/v1/privacy/data/{caller_hash}")
        response.raise_for_status()
        return response.json()

    def get_privacy_audit_log(self) -> Dict[str, Any]:
        """Returns a summary of what data is currently held and retention status."""
        response = self.client.get(f"{self.base_url}/api/v1/privacy/audit-log")
        response.raise_for_status()
        return response.json()
