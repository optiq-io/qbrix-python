#!/bin/bash
# Regenerate vendored gRPC stubs from ../qbrix/proto.
#
# Adapted from /Users/eskinmi/Dev/qbrix/bin/generate-proto.sh with two changes:
#   1. Output is namespaced under qbrix._transport._grpc._proto (not qbrixproto).
#   2. Sed import-rewrite pass runs on .pyi files too — the upstream script
#      skips these, which leaves type stubs broken for vendored consumers.
#
# Only proxy.proto + common.proto are vendored. auth.proto, motor.proto, and
# cortex.proto define internal service-to-service RPCs that SDK users never call.
#
# Usage:
#   bash bin/regen_protos.sh
#   QBRIX_PROTO_SRC=/path/to/qbrix/proto bash bin/regen_protos.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."

PROTO_SRC_DIR="${QBRIX_PROTO_SRC:-$ROOT_DIR/../qbrix/proto}"
OUT_DIR="$ROOT_DIR/qbrix/_transport/_grpc/_proto"
OUT_NAMESPACE="qbrix._transport._grpc._proto"

PROTO_FILES_TO_GEN=("common.proto" "proxy.proto")

# Pin grpcio-tools to keep protobuf 5.x-compatible stubs. grpcio-tools >=1.71.0
# emits protobuf 7.x stubs which conflict with the grpc python ecosystem's
# protobuf<7 pin (matches qbrix/bin/generate-proto.sh).
PROTO_GRPCIO_TOOLS_VERSION="1.76.0"
PROTO_VENV="$ROOT_DIR/.proto-venv"

cleanup() { rm -rf "$PROTO_VENV"; }
trap cleanup EXIT

if [[ ! -d "$PROTO_SRC_DIR" ]]; then
    echo "error: proto source directory not found: $PROTO_SRC_DIR" >&2
    echo "set QBRIX_PROTO_SRC to override (default: ../qbrix/proto relative to repo root)" >&2
    exit 1
fi

for f in "${PROTO_FILES_TO_GEN[@]}"; do
    if [[ ! -f "$PROTO_SRC_DIR/$f" ]]; then
        echo "error: $PROTO_SRC_DIR/$f not found" >&2
        exit 1
    fi
done

mkdir -p "$OUT_DIR"

echo "Source:    $PROTO_SRC_DIR"
echo "Output:    $OUT_DIR"
echo "Namespace: $OUT_NAMESPACE"

echo "Setting up proto generation environment (grpcio-tools==$PROTO_GRPCIO_TOOLS_VERSION)..."
uv venv "$PROTO_VENV" --python 3.10 -q
uv pip install --python "$PROTO_VENV/bin/python" -q \
    "grpcio-tools==$PROTO_GRPCIO_TOOLS_VERSION" \
    "mypy-protobuf"

PROTO_FILE_PATHS=()
for f in "${PROTO_FILES_TO_GEN[@]}"; do
    PROTO_FILE_PATHS+=("$PROTO_SRC_DIR/$f")
done

echo "Generating proto stubs..."
PATH="$PROTO_VENV/bin:$PATH" "$PROTO_VENV/bin/python" -m grpc_tools.protoc \
    --proto_path="$PROTO_SRC_DIR" \
    --python_out="$OUT_DIR" \
    --grpc_python_out="$OUT_DIR" \
    --mypy_out="$OUT_DIR" \
    "${PROTO_FILE_PATHS[@]}"

echo "Rewriting imports for vendored namespace..."

# BSD sed (macOS) needs an empty extension arg; GNU sed (linux) does not.
if [[ "$(uname)" == "Darwin" ]]; then
    SED_INPLACE=(sed -i '')
else
    SED_INPLACE=(sed -i)
fi

# Matches both:
#   .py:  import common_pb2 as common__pb2
#   .pyi: import common_pb2 as _common_pb2
SED_PATTERN="s|^import \\([a-z_]*_pb2\\) as |from $OUT_NAMESPACE import \\1 as |"

for ext in py pyi; do
    for file in "$OUT_DIR"/*."$ext"; do
        [[ -f "$file" ]] || continue
        "${SED_INPLACE[@]}" "$SED_PATTERN" "$file"
    done
done

echo "Done. Vendored stubs in $OUT_DIR"
echo "Generated files:"
ls -1 "$OUT_DIR" | grep -E '_pb2(_grpc)?\.(py|pyi)$' | sed 's/^/  /'
