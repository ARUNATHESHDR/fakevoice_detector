"""
gRPC server for the Voice Integrity Gateway.

Provides the same analysis capabilities as the REST API but over gRPC,
suitable for high-throughput telecom and enterprise integration where
sub-millisecond framing overhead matters.

Supports two RPC patterns:
  - AnalyzeStream: bidirectional streaming -- client sends audio chunks,
    server streams back a RiskAssessment after every processed window.
  - AnalyzeClip: unary -- client sends a short clip, server returns one
    aggregated RiskAssessment.

Runs alongside the REST gateway on port 50051.

Usage:
  python generate_proto.py   # once, to generate stubs
  python grpc_server.py      # starts the gRPC server
"""

import asyncio
import base64
import os
import uuid

import grpc
from grpc import aio
import httpx
import numpy as np

# Generated stubs -- run generate_proto.py first
import voice_analysis_pb2
import voice_analysis_pb2_grpc

GATEWAY_REST_URL = os.environ.get("GATEWAY_REST_URL", "http://localhost:8000")
GRPC_PORT = int(os.environ.get("GRPC_PORT", "50051"))

WINDOW_SECONDS = 2
SAMPLE_RATE = 16000
WINDOW_SIZE = WINDOW_SECONDS * SAMPLE_RATE


class VoiceIntegrityServicer(voice_analysis_pb2_grpc.VoiceIntegrityServiceServicer):

    async def AnalyzeClip(self, request, context):
        """One-shot analysis of a short pre-recorded clip."""
        pcm_int16 = np.frombuffer(request.pcm_data, dtype=np.int16)
        sample_rate = request.sample_rate or SAMPLE_RATE
        session_id = request.session_id or str(uuid.uuid4())

        results = []
        async with httpx.AsyncClient() as client:
            for i, start in enumerate(range(0, len(pcm_int16), WINDOW_SIZE)):
                window = pcm_int16[start : start + WINDOW_SIZE]
                if len(window) < sample_rate // 2:
                    break
                if len(window) < WINDOW_SIZE:
                    window = np.pad(window, (0, WINDOW_SIZE - len(window)))

                payload = {
                    "session_id": session_id,
                    "window_index": i,
                    "sample_rate": sample_rate,
                    "pcm_base64": base64.b64encode(window.tobytes()).decode(),
                }
                resp = await client.post(
                    f"{GATEWAY_REST_URL}/ingest/window", json=payload, timeout=10.0
                )
                results.append(resp.json())

        if results:
            final = results[-1]
            return voice_analysis_pb2.RiskAssessment(
                session_id=session_id,
                risk_score=final.get("risk_score", 0),
                spectral_score=final.get("spoof_score", 0),
                prosody_score=final.get("prosody_score", 0),
                consistency_score=final.get("consistency_score", 0),
                rationale=final.get("rationale", ""),
                alert_triggered=final.get("alert_triggered", False),
                recommended_action="",
            )

        return voice_analysis_pb2.RiskAssessment(session_id=session_id)

    async def AnalyzeStream(self, request_iterator, context):
        """Bidirectional streaming -- client sends audio chunks, server
        streams back a RiskAssessment after every processed window."""
        session_id = None
        buffer = np.array([], dtype=np.int16)
        window_index = 0

        async with httpx.AsyncClient() as client:
            async for chunk in request_iterator:
                if session_id is None:
                    session_id = chunk.session_id or str(uuid.uuid4())

                incoming = np.frombuffer(chunk.pcm_data, dtype=np.int16)
                buffer = np.concatenate([buffer, incoming])

                while len(buffer) >= WINDOW_SIZE:
                    window = buffer[:WINDOW_SIZE]
                    buffer = buffer[WINDOW_SIZE:]

                    payload = {
                        "session_id": session_id,
                        "window_index": window_index,
                        "sample_rate": chunk.sample_rate or SAMPLE_RATE,
                        "pcm_base64": base64.b64encode(window.tobytes()).decode(),
                    }
                    resp = await client.post(
                        f"{GATEWAY_REST_URL}/ingest/window",
                        json=payload,
                        timeout=10.0,
                    )
                    result = resp.json()
                    window_index += 1

                    yield voice_analysis_pb2.RiskAssessment(
                        session_id=session_id,
                        risk_score=result.get("risk_score", 0),
                        spectral_score=result.get("spoof_score", 0),
                        prosody_score=result.get("prosody_score", 0),
                        consistency_score=result.get("consistency_score", 0),
                        rationale=result.get("rationale", ""),
                        alert_triggered=result.get("alert_triggered", False),
                        recommended_action="",
                    )


async def serve():
    server = aio.server()
    voice_analysis_pb2_grpc.add_VoiceIntegrityServiceServicer_to_server(
        VoiceIntegrityServicer(), server
    )
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    print(f"gRPC server listening on port {GRPC_PORT}")
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
