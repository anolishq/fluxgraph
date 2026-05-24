#!/bin/bash
# Generate Python Protobuf Bindings (Linux/macOS)
#
# Usage:
#   ./scripts/generate_proto_python.sh [output-dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PROTO_FILE="$REPO_ROOT/proto/fluxgraph.proto"
PROTO_DIR="$REPO_ROOT/proto"

DEFAULT_OUTPUT_DIR="${FLUXGRAPH_PROTO_PYTHON_DIR:-$REPO_ROOT/build-server/python}"
OUTPUT_DIR="${1:-$DEFAULT_OUTPUT_DIR}"
mkdir -p "$OUTPUT_DIR"

echo "============================================"
echo "Generate Python Protobuf Bindings"
echo "============================================"
echo "Proto:       $PROTO_FILE"
echo "Output:      $OUTPUT_DIR"
echo "============================================"

# Check if proto file exists
if [ ! -f "$PROTO_FILE" ]; then
    echo "[ERROR] Proto file not found: $PROTO_FILE"
    exit 1
fi

# Find Python executable (prefer venv)
PYTHON_EXE=""
VENV_PATH="$REPO_ROOT/.venv"

if [ -f "$VENV_PATH/bin/python3" ]; then
    PYTHON_EXE="$VENV_PATH/bin/python3"
    echo "Using venv Python: $PYTHON_EXE"
elif [ -f "$REPO_ROOT/.venv-fxg/bin/python3" ]; then
    PYTHON_EXE="$REPO_ROOT/.venv-fxg/bin/python3"
    echo "Using venv Python: $PYTHON_EXE"
elif command -v python3 &>/dev/null; then
    PYTHON_EXE="python3"
else
    echo "[ERROR] Python not found. Install Python 3.8+ or activate venv."
    exit 1
fi

# Generate bindings
echo ""
echo "Generating bindings..."
"$PYTHON_EXE" -m grpc_tools.protoc \
    -I "$PROTO_DIR" \
    --python_out="$OUTPUT_DIR" \
    --grpc_python_out="$OUTPUT_DIR" \
    "$PROTO_FILE"

if [ $? -ne 0 ]; then
    echo "[ERROR] Code generation failed"
    echo "Install grpcio-tools: pip install grpcio-tools"
    exit 1
fi

echo ""
echo "[SUCCESS] Generated:"
echo "  - fluxgraph_pb2.py"
echo "  - fluxgraph_pb2_grpc.py"
echo ""
echo "Output directory: $OUTPUT_DIR"
