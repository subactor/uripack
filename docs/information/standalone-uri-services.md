---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "standalone-uri-services",
  "kind": "information",
  "version": 2,
  "title": "Standalone URI service packaging",
  "status": "implemented",
  "owner": "subactor/uripack",
  "created": "2026-09-08",
  "updated": "2026-09-08",
  "review_after": "2026-10-08",
  "source_revision": "fa416d94bbba5a099d8164a1aaa6f0bcb61c51d7",
  "affected_repositories": ["subactor/uripack"],
  "evidence": [
    "https://github.com/subactor/uripack/issues/1",
    "repo://subactor/uripack/src/uripack_refactor/services.py",
    "repo://subactor/uripack/tests/test_services.py",
    "repo://subactor/uripack/tests/test_integration.py",
    "repo://subactor/uripack/integration_tests/test_service_containers.py"
  ]
}
---

# Standalone URI service packaging

<!-- docs:section purpose -->
## Purpose

Issue #1 requests processes that own their implementation and runtime instead
of depending on an application checkout. An explicit service profile now adds
an independent Docker build context to each selected process package. HOME is
`subactor`; SHAPE is `runtime_service`. This is an uripack-owned contract,
not a claim of validated Wellmanifest DSL adoption.

<!-- docs:section scope -->
## Scope

The first runtime profiles support Python and Node, including already compiled
TypeScript running on Node. The operator selects whole files, one public URI,
the native entry command, dependency file and digest-pinned base image.
Application-specific HTTP servers and command-line processes keep their native
protocols. No generic HTTP wrapper, URI router or deployment controller is added.

<!-- docs:section evidence -->
## Evidence

The source revision in metadata identifies the imported baseline. This change
is implemented by `services.py`, its planner integration and the new v2 schemas;
`tests/test_services.py` covers planning, Guard admission and tampering.
`integration_tests/test_service_containers.py` contains the two real Docker cases.
The SDK conformance cases live in `tests/test_integration.py`.

Observed locally on 2026-09-08: **192 passed, 0 failed, 0 skipped**, including
both Docker services. The wheel was built and installed; its CLI validated the
v2 example. Wheel schema resources and sdist fixture completeness were checked.
The pinned Wellmanifest/docs 0.1.0 checker passed for this document.

Implementation SHA-256 (`src/uripack_refactor/services.py`):
`30a44d567ea6276cfaf8d8a8e9be152d0afbd7776c389a4c28b398b25e11cc27`.

Run the local suite, including actual container builds and requests:

```bash
python -m pytest -q tests integration_tests
```

Container tests build each fixture with network disabled, make the original
source path unavailable, and invoke two independent clients without bind mounts.
They check empty and Unicode inputs, the public URI, output count and UID 65532.
The extraction Guard is explicitly a test fake; Docker itself is real.
The ordinary suite (`make test`) runs 190 tests without Docker and without
conditional skips. `make test-docker` explicitly runs both Docker cases;
`make test-all` runs all 192. A missing Docker engine fails the integration
suite. Both suites and their shared fixtures are included in the sdist.

<!-- docs:section content -->
## Contract and usage

Use `uripack.refactor-request/v2`. Each unit may declare a closed `service`
profile with `schema: uripack.service-profile/v1` and these fields:

| Field | Meaning |
| --- | --- |
| `language` | `python` or `node` |
| `base_image` | Reviewed image reference ending in `@sha256:<64 hex digits>` |
| `workdir` | Selected source directory, relative to source root; `.` is allowed |
| `command` | Explicit nonempty argument array, emitted as exec-form ENTRYPOINT |
| `dependency_file` | Exact selected path, relative to source root |
| `ports` | Optional TCP port metadata; does not publish host ports |

A service unit must have exactly one `public_uris` entry found in its source.
Its runtime manifest references that identity rather than creating a second
URI owner. `depends_on` cannot supply another extracted tree to a standalone
service: choose native dependencies or explicit service clients instead.
Filesystem paths, selected dependencies, source hashes and generated output
are checked before admission and again during extraction.

The complete planning example is [standalone-services.yaml](../../examples/standalone-services.yaml):

```bash
uripack validate-request examples/standalone-services.yaml
uripack plan --request examples/standalone-services.yaml \
  --source examples/service-source \
  --target /tmp/uripack-services \
  --out /tmp/uripack-services-plan.json
uripack apply --plan /tmp/uripack-services-plan.json \
  --guard-config /etc/organism/uripack-bridge.json
uripack verify --plan /tmp/uripack-services-plan.json
```

The target and evidence paths must be unused. `apply` requires a real protected
adapter installed by the operator; these commands do not install one.
A service pack contains:

```text
packs/python-count/
├── uripack.json       # identity, contracts, dependencies, provenance and runtime
├── uri-baseline.json
├── Dockerfile
├── .dockerignore
└── tree/python/
    ├── main.py
    └── requirements.lock
```

After reviewing and admitting the generated artifact, the operator can build
and call a fixture using Docker directly:

```bash
docker build -t uripack-python-count /tmp/uripack-services/packs/python-count
printf '%s\n' '{"items":["a","b"]}' | \
  docker run --rm -i --network=none --read-only uripack-python-count
```

The native response contains `demo://services/python/count` and count `2`.
Any language capable of sending the native input can consume this process;
uripack and the original repository are not required in the running container.
The Node fixture works the same way using `packs/node-count`.

Python dependencies use pip hash checking and binary distributions only;
all dependencies must be present in the reviewed requirements lock with exact
versions and hashes. The fixture intentionally uses only the standard library.
Node requires both `package.json` and `package-lock.json` in its workdir and
uses `npm ci --omit=dev --ignore-scripts`. TypeScript must already be compiled
and selected, and dependencies requiring install scripts are outside this
profile. See the observed primary references for
[Dockerfile exec form and USER](https://docs.docker.com/reference/dockerfile/),
[pip hash checking](https://pip.pypa.io/en/stable/topics/secure-installs/), and
[npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/), reviewed 2026-09-08.

Builds may install dependencies; planning and extraction never run Docker or
package managers. Generated commands are reviewable plan content covered by
its digest. The image runs as UID/GID `65532:65532`; deployment-level resource,
network, secret, port and writable-volume policies belong to the operator.

## Compatibility and responsibility

V1 request and plan schema files remain unchanged. V1 rejects `service` rather
than silently losing it. V2 plans contain v2 requests and must be replanned
with a consumer that supports v2. Generated Docker inputs participate in the
same integrity and Guard checks as copied sources. There is no CLI bypass.
The TypeScript SDK accepts both versions; the existing LLM envelope and GBNF
continue to advertise v1 extraction only.

Single responsibility is a design obligation: one public URI is a structural
check, not proof that arbitrary code performs only one responsibility.
Single source of truth is the intended post-cutover ownership: this preparatory
extraction retains original files. Consumers must adopt the new process in a
separately verified cutover before the old implementation can be retired.

<!-- docs:section limitations -->
## Limitations

There is no automatic function decomposition, import rewriting, package-manager
lock generation, TypeScript compilation, image publishing or production URI
cutover. Missing transitive imports and native dependencies can still make a
build or invocation fail. Native lock validity is enforced by the package
manager during the build, not proven by the static planner.
Digest syntax validation does not authenticate an image's publisher. Review the
base image and dependencies; a Dockerfile and a successful fixture are not a
sandbox guarantee or evidence of production compatibility.

On 2026-09-08 the protected local CI profile was deployed from
[subactor/onedev-agent#230](https://github.com/subactor/onedev-agent/pull/230).
The publication profile is authored in SQLite and its projection and signer key
were independently approved in
[subactor/registry#47](https://github.com/subactor/registry/pull/47).
The deployed verifier from
[subactor/validator-agent#399](https://github.com/subactor/validator-agent/pull/399)
checks the signature and exact pins. These prerequisites are separate from
uripack's own independent publication and from production Guard integration.
This repository has no artifact-registry entry in Platform; new contracts are
validated by JSON Schema, their generator and the package tests. Documentation
placement follows Wellmanifest/docs, but protected CI adoption is unverified.

<!-- docs:section next_actions -->
## Next actions

Publish the material PR for #1 through the deployed local CI and signed SQLite
profile, preserving the independent Validator decision. A real service
pilot requires the operator's pinned image, native locked dependencies,
protected Guard checks and independent acceptance of the native interface.
Rollback before cutover is to keep using the unchanged original application;
no production routing changes are part of this implementation.
