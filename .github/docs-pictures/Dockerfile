# The terminal that records a copy of the blueprint for the documentation:
# scripts/docs-pictures.sh plays copier-copy.tape in the VHS of this image, with git
# and the Copier of the blueprint bot. Renovate keeps it current.
FROM ghcr.io/charmbracelet/vhs:v0.12.1@sha256:ea49a6a1c529be83153e88321892b5585964418f0b9055e8c1e0d732194234a3

# Copier clones the blueprint with git, and gifsicle makes the GIF smaller. Debian
# leaves the packages of its own Python to apt, so Copier gets a venv of its own.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git gifsicle python3-venv \
    && rm -rf /var/lib/apt/lists/*

# The same Copier as the blueprint bot's, pinned by hash. The build context is the
# root of the repository.
COPY stacks/copier/requirements.txt /tmp/copier-requirements.txt
RUN python3 -m venv /opt/copier \
    && /opt/copier/bin/pip install --no-cache-dir --require-hashes -r /tmp/copier-requirements.txt \
    && ln -s /opt/copier/bin/copier /usr/local/bin/copier

# The dry run of blueprint.py create at the end of the recording shows its commands
# only after its preflight, which asks for the identity of the first commit and for a
# GitHub CLI that is signed in. The recording has no secrets, so gh.sh answers for it.
COPY --chmod=755 .github/docs-pictures/gh.sh /usr/local/bin/gh
RUN git config --system user.name "Dennis Otto" \
    && git config --system user.email "Dennis-Otto@users.noreply.github.com"
