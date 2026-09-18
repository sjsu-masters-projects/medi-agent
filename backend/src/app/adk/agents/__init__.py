"""The workers, as agents on the new runtime.

One package per worker boundary in `.agent/ARCHITECTURE.md`, and no more: the four
boundaries are a product decision, and a fifth agent package would be a claim of a fifth
worker. Each package owns its agent definition, its instructions, and the tool allowlist
that `build_runner` enforces for it — kept together because an agent's name and its
allowlist key have to agree, and they are the kind of thing that drifts apart when they
live in different files.
"""
