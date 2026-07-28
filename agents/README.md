# Agent roster

Each file in this directory is an operating prompt for a specialist subagent. The registry defines the canonical scope; role files provide the working contract.

## How to dispatch

- Pick a role whose `status` is `ready` and whose dependencies are complete.
- Give the agent one milestone, the relevant acceptance criteria, and its owned paths.
- Require tests and a handoff note.
- Integrate through a branch/worktree and review the diff against `docs/SPEC.md`.

## Collision rule

Two agents must not edit the same path concurrently. Cross-cutting changes are proposed as contract patches and integrated by `lead-architect`.
