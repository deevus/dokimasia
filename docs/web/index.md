---
title: Evidence before rollout
hide:
  - toc
---

<section class="doki-hero">
  <p class="doki-kicker">Capability acceptance for agents</p>
  <h1>Evidence before rollout.</h1>
  <p class="doki-lede">
    Dokimasia is a pytest-first harness for testing whether an agent can use a real capability safely — and whether the world changed in the way the test required.
  </p>
  <div class="doki-actions">
    [Read the method](getting-started.md){ .md-button .md-button--primary }
    [View the API](api.md){ .md-button }
  </div>
</section>

<section class="doki-principles" aria-label="Acceptance evidence model">
  <article>
    <p class="doki-label">I. Claim</p>
    <h2>The agent says it can.</h2>
    <p>A suite names the capability: MCP server, CLI, skill, or workflow.</p>
  </article>
  <article>
    <p class="doki-label">II. Audit</p>
    <h2>The operation is observed.</h2>
    <p>Approved paths are checked through command spies, traces, and artifacts.</p>
  </article>
  <article>
    <p class="doki-label">III. Judgment</p>
    <h2>The external state agrees.</h2>
    <p>The domain oracle decides pass or fail. No vibes.</p>
  </article>
</section>

<section class="doki-verdict" aria-label="Judgment record">
  <p class="doki-label">Judgment record</p>
  <pre><code>capability evidence ......... present
audited operation ........... approved
independent domain oracle ... passed

VERDICT: ACCEPT</code></pre>
</section>

## What Dokimasia is for

Dokimasia is not a model benchmark and not just a trace viewer. It is CI-style acceptance testing for agent capabilities that mutate real systems.

Use it when a team needs evidence that an agent can use an approved capability correctly before that capability is rolled out to developers or employees.
