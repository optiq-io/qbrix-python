# Changelog

## [0.2.7](https://github.com/optiq-io/qbrix-python/compare/v0.2.6...v0.2.7) (2026-08-17)


### Features

* **grpc:** send policy_params as a Struct, not a string map (OPT-399) ([a706894](https://github.com/optiq-io/qbrix-python/commit/a70689421d349d31b589f6fb44c9d1a49cc4bedb))

## [0.2.6](https://github.com/optiq-io/qbrix-python/compare/v0.2.5...v0.2.6) (2026-08-17)


### Features

* send context.properties on both transports (OPT-388) ([28d1c90](https://github.com/optiq-io/qbrix-python/commit/28d1c9049b1902bb5f9246947269f3e2c94aa3bc))
* send context.properties on both transports (OPT-388) ([1a37650](https://github.com/optiq-io/qbrix-python/commit/1a37650bbfef7143c9d82cee23acc15038ec7793))

## [0.2.5](https://github.com/optiq-io/qbrix-python/compare/v0.2.4...v0.2.5) (2026-08-16)


### Bug Fixes

* gate.update sends only the fields you pass (OPT-355) ([fe27ffa](https://github.com/optiq-io/qbrix-python/commit/fe27ffa30c62b9f63776cf0f5eb541fe0c67cf99))

## [0.2.4](https://github.com/optiq-io/qbrix-python/compare/v0.2.3...v0.2.4) (2026-08-16)


### Documentation

* **examples:** runnable scripts backing the use-case docs (OPT-350) ([543d5ba](https://github.com/optiq-io/qbrix-python/commit/543d5ba816bd8d44bcf18f7286f16fb87673e8ca))
* **examples:** runnable scripts backing the use-case docs (OPT-350) ([157d9dd](https://github.com/optiq-io/qbrix-python/commit/157d9dd76eda6ea5d926295b666b487104c8d5e9))

## [0.2.3](https://github.com/optiq-io/qbrix-python/compare/v0.2.2...v0.2.3) (2026-07-01)


### Features

* add experiment.reset() and make SelectResponse.request_id optional ([88325a7](https://github.com/optiq-io/qbrix-python/commit/88325a7098ee4f445dce05c5f204bb2a9ad0c48c))
* add experiment.reset() and make SelectResponse.request_id optional ([5947d63](https://github.com/optiq-io/qbrix-python/commit/5947d63d0dcc066e083fbf966acc660d2e556157))

## [0.2.2](https://github.com/optiq-io/qbrix-python/compare/v0.2.1...v0.2.2) (2026-05-31)


### Features

* updated the mcp implementation to V2 ([24a2809](https://github.com/optiq-io/qbrix-python/commit/24a280941673faea43de3a4b12b234b69193fa8b))


### Bug Fixes

* install mcp extra in dev deps so CI can import the mcp server ([a043377](https://github.com/optiq-io/qbrix-python/commit/a0433771c523282ed132a252af776f9348ffbbe1))

## [0.2.1](https://github.com/optiq-io/qbrix-python/compare/v0.2.0...v0.2.1) (2026-05-21)


### Features

* added unimplemented error to grpc transport ([9021820](https://github.com/optiq-io/qbrix-python/commit/9021820db7f99f0b4d65329d06aa39a1f32afb3a))
* remove auth api / unused and broken ([b6a4eea](https://github.com/optiq-io/qbrix-python/commit/b6a4eea3a476ba5f633e3f52415f9b66e81a2eeb))
* support the policy resource over the gRPC transport ([d6277f1](https://github.com/optiq-io/qbrix-python/commit/d6277f1bb3f6cd20aa9e7b806de48ec6afdd9d12))

## [0.2.0](https://github.com/optiq-io/qbrix-python/compare/v0.1.7...v0.2.0) (2026-05-19)


### ⚠ BREAKING CHANGES

* add gRPC transport alongside HTTP

### Features

* add gRPC transport alongside HTTP ([4cd0f2e](https://github.com/optiq-io/qbrix-python/commit/4cd0f2ed2b1c1768cfd48f383f1fad6491d094fa))

## [0.1.7](https://github.com/optiq-io/qbrix-python/compare/v0.1.6...v0.1.7) (2026-04-28)


### Features

* auth resource for API key management ([d59a962](https://github.com/optiq-io/qbrix-python/commit/d59a9628d6361ee4542cf70f02b2ee40f467d9f1))
* config validation, improved defaults, http2 and pool limit settings ([86776e0](https://github.com/optiq-io/qbrix-python/commit/86776e0d44c9c5f990b675fcb4593033bfb706e1))
* honor retry-after header and add user agent ([e75349e](https://github.com/optiq-io/qbrix-python/commit/e75349e73ff8588a7bb42714bcb269b000a5739e))
* policy name literal type added and iter_all pagination helpers ([52dd483](https://github.com/optiq-io/qbrix-python/commit/52dd4839deff742700fa9b236ac533d920b07382))
* runtime health resources added ([7cd0293](https://github.com/optiq-io/qbrix-python/commit/7cd02930251798f5370229d970f3382ae7c6ef0c))


### Bug Fixes

* map 502 and 504 to typed exception ([314819d](https://github.com/optiq-io/qbrix-python/commit/314819dc8d5f5ab7153b347171b2315dc07d4013))
* thread-safe module level client singleton implementation ([3638a01](https://github.com/optiq-io/qbrix-python/commit/3638a012515a80b3359f4d45ad17f286160e3283))

## [0.1.6](https://github.com/optiq-io/qbrix-python/compare/v0.1.5...v0.1.6) (2026-04-12)


### Features

* sync SDK with upstream proxy schema changes ([03fa6c2](https://github.com/optiq-io/qbrix-python/commit/03fa6c2268423e9397450e8c429fd503459f4601))

## [0.1.5](https://github.com/optiq-io/qbrix-python/compare/v0.1.4...v0.1.5) (2026-03-16)


### Features

* added .env support to qbrix ([3e6d96b](https://github.com/optiq-io/qbrix-python/commit/3e6d96b119fb0e002a4ddc9d28d5f30ded1a6d68))
* update auto sync in release flow ([b26a942](https://github.com/optiq-io/qbrix-python/commit/b26a942e00e90cc90c1faea17a9015fe74370cc0))

## [0.1.4](https://github.com/optiq-io/qbrix-python/compare/v0.1.3...v0.1.4) (2026-03-14)


### Features

* created init mcp server ([e303507](https://github.com/optiq-io/qbrix-python/commit/e303507a0a21106772f392a1e51b4d43d4e4895e))
* created init mcp server ([8e362dd](https://github.com/optiq-io/qbrix-python/commit/8e362dd8654c010623f5480bcc008a84678744de))

## [0.1.3](https://github.com/optiq-io/qbrix-python/compare/v0.1.2...v0.1.3) (2026-03-12)


### Features

* create release github app and integrate ([6ecbf3b](https://github.com/optiq-io/qbrix-python/commit/6ecbf3b2f4c2bc1de61c094913e4b485dc346090))

## [0.1.2](https://github.com/optiq-io/qbrix-python/compare/v0.1.1...v0.1.2) (2026-03-05)


### Features

* created mod client and lazy proxy implementations ([e520223](https://github.com/optiq-io/qbrix-python/commit/e52022372ad48153168a6568f5929c0e6c8b389c))
* match proxy gate svc endpoint model changes to the sdk ([7d2e0a2](https://github.com/optiq-io/qbrix-python/commit/7d2e0a252f9183a470af88d8559d949da7be3d34))
* moved the resource file to base ([06dec0d](https://github.com/optiq-io/qbrix-python/commit/06dec0de9718afb0cfe1063142f2cccd80ec8e8a))
* update base client add deps ([97983d9](https://github.com/optiq-io/qbrix-python/commit/97983d9d531127d88cda44ae3c51fbc17b6e59f2))
* update ci flow to add automated test coverage ([db5f985](https://github.com/optiq-io/qbrix-python/commit/db5f9851e9c2caf3b8fbd33a8d94e302588dec1f))

## [0.1.1](https://github.com/optiq-io/qbrix-python/compare/v0.1.0...v0.1.1) (2026-03-01)


### Features

* update README.md ([d4106c4](https://github.com/optiq-io/qbrix-python/commit/d4106c4d78fc7515c56093a7cdb9ce1882ba6350))
