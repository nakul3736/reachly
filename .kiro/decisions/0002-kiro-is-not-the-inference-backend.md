# 0002 — Kiro builds Reachly; it does not run inside it

Status: Accepted · 2026-08-11

## Context

Reachly needs language-model calls at runtime, for resume parsing, tailoring, and
draft generation. The intent was to avoid paying for an Anthropic API key by
using the Kiro API key instead, since the hackathon supplies Kiro credits.

This conflates two different things. Kiro is the tool used to *build* Reachly.
It is not an inference endpoint that Reachly can call while serving users.

Kiro's pricing terms state that subscriptions "can be used with Kiro IDE, Kiro
CLI, Kiro on the web, ACP compatible IDEs, and automation in software development
(ex: reviews during CI/CD)," and that "use with OpenClaw and similar tools that
leverage third-party harnesses is prohibited." `KIRO_API_KEY` exists, but it is
documented for headless CLI use in CI/CD pipelines — code review, test
generation, build troubleshooting. Kiro is licensed as AWS Content under the AWS
Customer Agreement.

Routing end-user requests through Kiro would therefore breach the sponsor's own
terms inside the sponsor's hackathon, engaging Rule 11 and Rule 26.

## Decision

Kiro is the development environment. Reachly carries its own inference provider.

Runtime calls go through a narrow `LLMClient` interface with three
implementations: a Gemini client for production, a fixture client for
`DEMO_MODE`, and a null client that raises clearly if called when unconfigured.

Google's Gemini free tier is the default: roughly 1,000 requests per day with no
credit card, which comfortably covers a demo and costs nothing. The interface
exists so this is a swap, not a rewrite.

## Rejected

**Kiro as the inference backend.** Prohibited by its terms, as above.

**Shelling out to `kiro-cli` from the API layer.** Technically possible and a
plain circumvention of the same terms. Also unsuitable: one prompt per process
launch, no concurrency story, and a hard dependency on a developer tool being
installed on a production host.

**Anthropic API directly.** No free tier, needs prepaid credit. Kept as a
configuration option because the adapter makes it trivial, but not the default.

**Groq.** Faster and generous, but tailoring quality is the product's headline
claim and it is the one place output quality is directly visible to a judge.

## Consequences

- `LLMClient` must exist before any feature depends on model output, so it lands
  on day one.
- The fixture implementation is what makes `DEMO_MODE` possible, so demo mode is
  a by-product of this decision rather than separate work.
- The README must document that Kiro was used to build the project and Gemini to
  run it, since conflating the two would misrepresent the submission.
- Every model call site must tolerate provider failure. Deterministic behaviour
  is preferred wherever it is achievable — see
  [0003](0003-deterministic-scoring-over-llm.md).
