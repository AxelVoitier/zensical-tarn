# Tarn source archive build, version 1

This build type identifies the source archive stage in `release-build.yml`.
The coordinator must call that reusable workflow through a local workflow reference.
Both workflows and the trusted helpers come from the same reviewed product tag commit.
The trusted caller supplies the frozen tag ref target OID and its type as required inputs.
The workflow is not yet connected to the coordinator.

The unprivileged job invokes `build_sdist` from `prepare_release.py`.
That shared function checks the clean tagged source and installed release tools.
It builds the source archive from an independent clone.
The build uses the source commit timestamp, `PYTHONHASHSEED=0` and `TZ=UTC`.
The release dependency group pins the backend tools.
The workflow pins Python 3.12.12 and Hatch 1.18.1.

A fresh signing job receives only the source archive through an identified artifact.
It runs trusted helpers and pinned actions on `ubuntu-24.04`, without restored caches.
It has read access to source and artifacts, plus signing and attestation authority.
It has no publisher environment or package execution step.
Checkout credentials are not persisted in either job.
The signer uses Python 3.12.12 and requires GitHub CLI 2.99.0.
If the runner supplies another CLI version, the job stops.
Availability of these runtimes on the hosted runner remains untested.

The helper checks repository, tag, commit and coordinating workflow against platform context.
It reads the source tree, timestamp, tag target and target type through Git.
Both build and signing jobs require the independently observed target/type to match the frozen caller selection.
Replacing an annotated tag object at the same commit therefore stops advancement.
Annotated tags retain their tag object identity.
Lightweight tags retain their actual commit target and type.
It reads tool pins as data from the selected Git revision, without backend hooks.

The signer checks the artifact ID, run ID, attempt-specific artifact name and source revision.
It checks that the producer repository matches the current repository ID.
It compares the downloaded ZIP digest with the platform artifact digest.
The ZIP must contain only the expected `zensical_tarn-VERSION.tar.gz` member.
The archive must be nonempty and at most 1 MiB.
The helper copies that member as data and computes its SHA-256 digest independently.
It never extracts or executes the source archive.

The statement has exactly one filename and SHA-256 subject.
Its external parameters record the frozen source, workflow and toolchain identities.
Its internal parameters retain producer run, attempt, artifact and transport identities.
Its resolved dependency is the tagged source commit.
The archive SHA-256 identifies package bytes independently of the transport digest.
The action signs the helper's predicate with the selected archive as its sole subject.
No caller predicate, command, helper path or secret input is accepted.

After signing, the helper downloads and checks the producer artifact again.
It verifies the original bundle through `gh attestation verify`.
The certificate policy requires the repository, reusable signer workflow, exact signer revision,
source commit and source tag. It rejects self-hosted runners.
The helper then compares the verified statement with its independently constructed policy.
The output artifact retains the archive, selection record and original signed bundle.
It does not replace that bundle with an unsigned report.

Local tests cover source selection, transport and statement substitution, and verifier failures.
The signature fixture uses a local OpenSSL key at the external verifier boundary.
It proves rejection of changed signed bytes in that local fixture.
It does not test Sigstore trust roots, GitHub certificates or real runner isolation.
Hosted signing, certificate identities, artifact API behaviour and registry compatibility remain unrun.
These checks require separate remote authorisation before any SLSA level claim.
