# Tarn wheel provenance profile, version 1

This profile records the wheel produced by the tagged release workflow.
It uses GitHub's [workflow build type](https://actions.github.io/buildtypes/workflow/v1).
The external parameters identify the complete coordinating workflow.
Protected internal parameters identify the wheel stage and its selected inputs.
The reusable builder and its caller use the same frozen product-tag commit.
The coordinator admits the frozen tag before calling the reusable builder.
No hosted execution or SLSA level is established by local fixtures.

The unprivileged `wheel` job receives artifact IDs from the workflow dependency graph.
It retrieves the original sdist and its original signed bundle through the platform API.
The helper checks producer run, attempt, repository, commit, artifact name, ID and transport digest.
It compares the signed selection record with an independently constructed record.
It checks the source signature and protected source fields before package execution.
The helper hashes the selected sdist and passes its path and digest to a fixed build command.

`build_wheel.py` calls the shared `prepare_release.build_wheel` function.
That function freezes the input bytes and rejects a different digest before extraction.
It extracts the selected archive outside Git and builds with the pinned release toolchain.
Checkout sources do not supply wheel contents.
The build uses the frozen source timestamp, `PYTHONHASHSEED=0` and `TZ=UTC`.
The job has read permissions and no signing, publishing or release-write authority.

A fresh `attest-wheel` job independently retrieves both original archives.
It repeats the source selection and signature checks and hashes the selected wheel.
It executes trusted helpers and pinned actions without package hooks or restored caches.
Its permissions allow source/artifact reads and signing, with no publisher environment.
Python, Hatch and GitHub CLI pins match the source archive build profile.
The hosted availability and isolation of those runtimes remain untested.

The wheel statement has exactly one wheel filename and SHA-256 subject.
Its protected source, builder and toolchain identities match the source statement.
Its resolved dependencies include the source commit and exact sdist filename and SHA-256.
Its internal parameters retain both original archive transport identities.
They preserve the original GitHub event, repository and owner IDs, and hosted-runner identity.
Both archives must belong to the same original execution and platform context.
Verification on a later resume uses that retained context.
The sdist digest must match the verified source statement subject.
Two independent signed output digests do not satisfy this relationship.
No build-produced report, command or predicate can choose these protected fields.

The signing job retains the original wheel bundle and selected wheel.
A separate `freeze` job retrieves and compares the original archives and signed copies.
It verifies both signatures and protected statements before freezing the selection.
The canonical manifest records both archive sizes/digests, original evidence IDs/digests,
source identity, transport identities and exact wheel input digest.

Shared checks receive the selected manifest digest and identified candidate artifact.
Each Python matrix job checks those bytes and installs the selected wheel.
The browser job also installs the selected wheel.
CSS, regression and configuration checks remain distinct checks of the frozen checkout.
The reproduction job uses shared preparation to build twice independently.
Both reproduced archive pairs must match the selected pair byte for byte.
The reusable workflow exposes the original candidate only after both gates pass.

Hosted signatures, certificate identities, artifact API behaviour and matrix execution
require separate remote proof. Local signatures use temporary OpenSSL keys.
They test policy and signature rejection without claiming GitHub certificate verification.
