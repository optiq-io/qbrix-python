.PHONY: proto proto-check test fmt typecheck

# Regenerate vendored gRPC stubs from ../qbrix/proto.
# Override source location with QBRIX_PROTO_SRC=/path/to/qbrix/proto.
proto:
	bash bin/regen_protos.sh

# Verify vendored stubs are up to date. Use in CI.
proto-check:
	bash bin/regen_protos.sh
	git diff --exit-code qbrix/_transport/_grpc/_proto

test:
	uv run pytest

fmt:
	uv run black .

typecheck:
	uv run mypy qbrix/
