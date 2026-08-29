"""Run once to generate Python gRPC stubs from voice_analysis.proto.
Called automatically by setup.bat."""

import subprocess
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

subprocess.run(
    [
        sys.executable, "-m", "grpc_tools.protoc",
        "-I.", "--python_out=.", "--grpc_python_out=.",
        "voice_analysis.proto",
    ],
    check=True,
)
print("Generated voice_analysis_pb2.py and voice_analysis_pb2_grpc.py")
