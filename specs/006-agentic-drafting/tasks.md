# Tasks: Agentic Drafting (Evidence-Cited Personalized Copy)

**Feature**: 006-agentic-drafting | **Date**: 2026-07-20
**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Total**: 52 tasks (T001–T052) across 8 phases.

Every task carries a concrete acceptance check (Principle VII): a pytest node, a
CLI invocation, or an observed file. No task is checked off on inspection alone.

**Phase ordering note**: User Story 3 (freeze) runs before User Story 1 (the
feature core) despite equal P1 priority. The 27 already-sent notes in the live
vault are exposed to draft-rewriting the moment any re-run happens, and the fix
is small and self-contained. Protect live data first.

---

## Phase 1: Setup

**Goal**: Package plumbing and the data structures every later phase needs.

- [X] T001 Add `prospector/agent/**/*.md` to `[tool.setuptools.package-data]` in `pyproject.toml` alongside the existing `data/*.txt` entry
  **Accept**: `pip install -e . && python -c "from importlib.resources import files; print(files('prospector').joinpath('agent/IDENTITY.md'))"` resolves without error once T009 lands
- [X] T002 [P] Add `DraftBlock` dataclass (`text: str`, `cites: list[str]`) to `prospector/models.py` per data-model.md
  **Accept**: `pytest tests/unit/test_models.py -q` passes
- [X] T003 [P] Add `EvidenceRef` dataclass (`id`, `kind`, `value`, `source`, `excerpt`) to `prospector/models.py`
  **Accept**: `pytest tests/unit/test_models.py -q` passes
- [X] T004 [P] Add `AgentResponse` dataclass (`subject: str`, `blocks: list[DraftBlock]`) to `prospector/models.py`
  **Accept**: `pytest tests/unit/test_models.py -q` passes
- [X] T005 Add `source: str = "template"` field to the existing `Draft` dataclass in `prospector/models.py`
  **Accept**: `pytest tests/unit/test_draft.py -q` passes **unmodified** (first checkpoint for FR-316)
- [X] T006 Add `drafted_agent: int`, `drafted_template: int`, `fallback_reasons: list[tuple[str, str]]` to `RunSummary` in `prospector/models.py`
  **Accept**: `pytest tests/unit/test_models.py::test_run_summary_reconciles -q` passes

**Checkpoint**: `pytest tests/ -q` fully green; no behavior changed yet.

---

## Phase 2: User Story 3 — Approved and sent copy is frozen (P1) 🛡️

**Goal**: A re-run can never rewrite copy the operator approved or copy that was
already mailed.

**Independent test**: Seed a vault with one note per status, run the batch,
confirm only the `to-send` note's draft changed.

**Why first**: This repairs a latent defect in `merge_notes` (Draft always comes
from fresh) that the chosen "re-draft everything" rollout would fire against 27
live sent notes.

- [X] T007 [US3] Add `read_status(vault_dir, slug) -> str | None` and `is_frozen(status) -> bool` to `prospector/vault.py` per contracts/note-format.md §3; unknown statuses are frozen (default down)
  **Accept**: `pytest tests/unit/test_vault_freeze.py::test_is_frozen_defaults_down -q`
- [X] T008 [US3] Add `freeze_draft: bool = False` keyword to `merge_notes()` in `prospector/vault.py`; when set, `## Draft` and `draft_source` come from `existing`, everything else unchanged
  **Accept**: `pytest tests/unit/test_vault_freeze.py -q`
- [X] T009 [US3] Thread `freeze_draft` through `upsert_note()` in `prospector/vault.py`
  **Accept**: `pytest tests/unit/test_vault.py -q` passes unmodified
- [X] T010 [US3] In `prospector/pipeline.py`, read note status **before** drafting; when frozen, skip drafting entirely (no model call) and pass `freeze_draft=True` to the write
  **Accept**: `pytest tests/unit/test_pipeline_freeze.py::test_no_llm_call_for_frozen -q` with respx asserting call count == 0
- [X] T011 [P] [US3] Write `tests/unit/test_vault_freeze.py`: frozen note keeps `## Draft` byte-identical; `## Research` still refreshes; `status: hold` is treated as frozen; key order stays stable
  **Accept**: `pytest tests/unit/test_vault_freeze.py -q` — 4+ cases pass
- [X] T012 [P] [US3] Write `tests/unit/test_pipeline_freeze.py`: zero model calls for an approved-only vault; `to-send` note is re-drafted in the same run
  **Accept**: `pytest tests/unit/test_pipeline_freeze.py -q`
- [X] T013 [US3] Verify against a copy of the live vault: copy `Vault/Outreach` to a temp dir, run the batch, confirm all 27 `status: sent` notes have byte-identical `## Draft` sections
  **Accept**: `diff <(git show HEAD:Vault/Outreach/<sent-slug>.md) /tmp/vaultcopy/<sent-slug>.md` shows no Draft-section change for every sent slug

**Checkpoint**: SC-306 satisfied — zero approved/sent notes alterable by any re-run. Safe to proceed.

---

## Phase 3: Foundational — Instruction files and loading

**Goal**: The operator's copy strategy exists as versioned content, loads once
per run, and fails loudly when broken. Blocking prerequisite for US1.

- [ ] T014 [P] Write `prospector/agent/IDENTITY.md` — who the sender is (Anas, Founder, Omniveer), voice, what he is not (no hype, no urgency)
  **Accept**: file exists, non-empty, contains no secrets (`grep -riE 'api[_-]?key|password|token' prospector/agent/` returns nothing)
- [ ] T015 [P] Write `prospector/agent/OFFER.md` — the free 10-day pilot for 5 duct-cleaning companies, the Duct Lead Qualifier's capabilities, and the single permitted link `https://www.omniveer.com/duct-lead-qualifier`
  **Accept**: file exists; contains exactly one URL (`grep -o 'https\?://' prospector/agent/OFFER.md | wc -l` == 1)
- [ ] T016 [P] Write `prospector/agent/CONSTRAINTS.md` — hard rules restated for the model: cite every block, never claim ad-running, never assert their Facebook usage without an `fb_*` citation, exactly one link, no LinkedIn, no attachments, plain text
  **Accept**: file exists and names each rule that has a corresponding validator check in contracts/agent-draft.md §5
- [ ] T017 [P] Write `prospector/agent/skills/write-cold-email.md` — structure, opening lines that work, length target, how to use a hook, when to say less
  **Accept**: file exists, non-empty
- [ ] T018 Create `prospector/instructions.py` with `MAX_INSTRUCTION_CHARS = 20_000`, `REQUIRED_FILES` in fixed load order, and `load_instructions() -> InstructionSet` using `importlib.resources` (mirroring `source.load_metros`)
  **Accept**: `pytest tests/unit/test_instructions.py::test_loads_all_four -q`
- [ ] T019 Raise `ConfigError` naming the file when a required instruction file is missing or unreadable, in `prospector/instructions.py`
  **Accept**: `pytest tests/unit/test_instructions.py::test_missing_file_names_it -q`
- [ ] T020 Raise `ConfigError` reporting actual size and cap when assembled instructions exceed `MAX_INSTRUCTION_CHARS`; never truncate (FR-325)
  **Accept**: `pytest tests/unit/test_instructions.py::test_oversize_fails_loudly -q`
- [ ] T021 Add `Settings.require_instructions()` pre-flight to `prospector/config.py` and call it from the `run` command in `prospector/cli.py` before any company is processed
  **Accept**: `mv prospector/agent/OFFER.md /tmp/ && prospector run samples/live_smoke.local.csv; echo $?` prints the filename and exits `1` with no note written; restore afterwards
- [ ] T022 [P] Write `tests/unit/test_instructions.py` and fixture files under `tests/fixtures/agent/`
  **Accept**: `pytest tests/unit/test_instructions.py -q` — 4+ cases pass

**Checkpoint**: Instruction content loads, bounds, and fails loudly. No model call yet.

---

## Phase 4: User Story 1 — Personalized copy that cannot invent facts (P1) ⭐ MVP

**Goal**: The model writes cited prose; a deterministic validator resolves every
citation before the copy reaches a note.

**Independent test**: Fixture company with known evidence + stubbed model
response → note contains model prose whose personalized statements each cite a
real record for that company.

- [ ] T023 [US1] Add `build_evidence_refs(research) -> list[EvidenceRef]` to `prospector/agent_draft.py` assigning `<kind>_<ordinal>` ids over `name_evidence + fb_evidence + [hook_evidence]` per research R1
  **Accept**: `pytest tests/unit/test_agent_draft.py::test_evidence_ids_stable -q` — same research twice yields identical ids
- [ ] T024 [US1] Add `build_payload(prospect, refs) -> dict` to `prospector/agent_draft.py` — company, resolved greeting, city, evidence catalogue, `offer_id`. Raw HTML MUST NOT appear (FR-302)
  **Accept**: `pytest tests/unit/test_agent_draft.py::test_payload_excludes_html -q`
- [ ] T025 [US1] Add `request_draft(prospect, settings, instructions) -> AgentResponse` to `prospector/agent_draft.py` — one POST, temperature 0.7, `json_object` response format, 60s timeout, reusing `draft._strip_code_fences`
  **Accept**: `pytest tests/unit/test_agent_draft.py::test_single_request -q` with respx call count == 1
- [ ] T026 [US1] Add response parsing with the rejection table from contracts/agent-draft.md §3 (non-object, missing subject, block count outside 3–6, malformed block)
  **Accept**: `pytest tests/unit/test_agent_draft.py -k parse -q` — one case per rejection row
- [ ] T027 [US1] Add `assemble_body(prospect, response) -> str` — greeting from `expected_greeting()` (code, never the model), blocks joined by blank lines, existing `SIGNATURE` appended
  **Accept**: `pytest tests/unit/test_agent_draft.py::test_assembly_golden -q` against a fixed stub response
- [ ] T028 [US1] Implement citation rule **V1** (every block has ≥1 citation) in `prospector/agent_draft.py`
  **Accept**: `pytest tests/unit/test_agent_draft.py::test_v1_empty_cites_rejected -q`
- [ ] T029 [US1] Implement citation rule **V2** (every citation is `offer` or a real `EvidenceRef.id` for this company)
  **Accept**: `pytest tests/unit/test_agent_draft.py::test_v2_unknown_id_rejected -q`
- [ ] T030 [US1] Implement citation rule **V3** — the anti-laundering rule: an offer-only block may not contain the company name or a distinctive token from it, the resolved city, `name_used`, `name_candidate`, or the hook value
  **Accept**: `pytest tests/unit/test_agent_draft.py::test_v3_offer_only_block_with_company_name_rejected -q`
- [ ] T031 [US1] Implement citation rule **V4** — at least one block cites a non-`offer` id, else the draft is template-equivalent and the template is used
  **Accept**: `pytest tests/unit/test_agent_draft.py::test_v4_all_offer_falls_back -q`
- [ ] T032 [US1] Apply retained checks **V5–V12** to the assembled body by reusing `draft.py`'s existing predicates (banned ad vocabulary, one link == product URL, no LinkedIn, signature intact, no `[slot]`, greeting prefix, name traceability, subject tokens)
  **Accept**: `pytest tests/unit/test_agent_draft.py -k retained -q` — one case per rule
- [ ] T033 [US1] Collect **all** failing rules rather than short-circuiting, into `Draft.validation_errors` (FR-314)
  **Accept**: `pytest tests/unit/test_agent_draft.py::test_all_reasons_collected -q` — a doubly-invalid response reports both
- [ ] T034 [P] [US1] Write `tests/unit/test_agent_draft.py` covering T023–T033
  **Accept**: `pytest tests/unit/test_agent_draft.py -q` — 20+ cases pass
- [ ] T035 [US1] Wire `agent_draft.draft_email()` into `prospector/pipeline.py` for email-channel, non-frozen companies; messenger path untouched (FR-308)
  **Accept**: `pytest tests/integration/test_batch_run.py -q` passes; messenger notes still show zero model calls

**Checkpoint**: MVP. Personalized cited copy reaches notes; SC-302 and SC-303 demonstrable.

---

## Phase 5: User Story 2 — The locked template always answers (P1)

**Goal**: Every failure mode lands on a working, honest draft, and the failure is visible.

**Independent test**: Force each failure mode; note still written, honest, marked `template`, counted.

- [ ] T036 [US2] Implement `draft_email()` fallback coordinator in `prospector/agent_draft.py` — never raises (G1), returns `draft.build_email_draft(...)` with `source="template"` on any failure
  **Accept**: `pytest tests/integration/test_agent_fallback.py::test_never_raises -q` parametrized over every failure mode
- [ ] T037 [US2] Skip the model entirely when the evidence catalogue is empty (G3, FR-317), reason `no evidence to cite`
  **Accept**: `pytest tests/integration/test_agent_fallback.py::test_no_evidence_no_request -q` with respx call count == 0
- [ ] T038 [US2] Set `draft_source` frontmatter from `Draft.source` in `prospector/vault.py:render_note`
  **Accept**: `pytest tests/unit/test_vault.py -k draft_source -q`
- [ ] T039 [US2] Count `drafted_agent` / `drafted_template` and append `(slug, reason)` to `fallback_reasons` in `prospector/pipeline.py`
  **Accept**: `pytest tests/integration/test_agent_fallback.py::test_summary_counts -q`
- [ ] T040 [US2] Print drafting-path counts and the fallback list in `prospector/cli.py:_print_summary`
  **Accept**: `prospector run samples/live_smoke.local.csv --verbose` prints `drafted by agent: N   by template: M` and a fallback list
- [ ] T041 [P] [US2] Write `tests/integration/test_agent_fallback.py` — transport error, malformed JSON, bad block count, citation failure, retained-check failure, empty evidence
  **Accept**: `pytest tests/integration/test_agent_fallback.py -q` — 6+ cases pass
- [ ] T042 [US2] Verify SC-305: run the full batch with the OpenRouter host unreachable and confirm output matches template-only output
  **Accept**: `pytest tests/integration/test_agent_fallback.py::test_total_outage_matches_template_output -q`

**Checkpoint**: SC-304 and SC-305 satisfied. The honesty floor holds under total model failure.

---

## Phase 6: User Story 4 — Tuning the voice without touching code (P2)

**Goal**: Editing markdown changes the produced copy; no code, no tests, no reinstall.

**Independent test**: Change a line in `OFFER.md`, re-run one company, observe the change.

- [ ] T043 [US4] Verify the edit loop end to end: modify a sentence in `prospector/agent/OFFER.md`, re-run one company, confirm the produced draft reflects it with `git status` showing no `.py` change
  **Accept**: `prospector run samples/live_smoke.local.csv --only <slug> --verbose` then `git diff --name-only` lists only the `.md` file and the vault note
- [ ] T044 [P] [US4] Add a test asserting instruction content reaches the request body, so an edit cannot silently stop taking effect
  **Accept**: `pytest tests/unit/test_agent_draft.py::test_instructions_reach_system_message -q`

**Checkpoint**: SC-307 satisfied.

---

## Phase 7: User Story 5 — Knowing whether it worked (P3)

**Goal**: Each note records its drafting path and the operator's recorded outcome; the dashboard compares them.

**Independent test**: Set outcomes by hand across both sources; dashboard groups them correctly.

- [ ] T045 [US5] Add `outcome` to `FRONTMATTER_KEYS` in `prospector/vault.py` (after `needs_review`, before `tags`), written empty on creation and never again
  **Accept**: `pytest tests/unit/test_vault.py -k outcome -q`
- [ ] T046 [US5] Preserve `outcome` from the existing note in `merge_notes()` — the same rule already proven for `status` (FR-332)
  **Accept**: `pytest tests/unit/test_vault.py::test_outcome_preserved_across_rerun -q`
- [ ] T047 [P] [US5] Append the two Dataview queries from contracts/note-format.md §4 to `DASHBOARD_CONTENT` in `prospector/vault.py`
  **Accept**: `prospector dashboard` then `grep -c 'GROUP BY draft_source' Vault/Outreach/_Dashboard.md` returns 2; `pytest tests/unit/test_dashboard.py -q` passes

**Checkpoint**: SC-308 satisfied — reply rate comparable by drafting path.

---

## Phase 8: Polish & Documentation Reconciliation

**Goal**: Close the ⚠ pending items Constitution v5.0.0 raised. Required before the feature is marked complete.

- [ ] T048 [P] Update `PRODUCT.md` §8 — replace locked-template drafting language with the cited-blocks model, retaining the template as documented fallback
  **Accept**: `grep -n "cite" PRODUCT.md` shows the new §8 language; no stale "fills bracketed slots only" claim remains outside the fallback description
- [ ] T049 [P] Update `README.md` guarantees #3 and #4 — reframe from "never fabricates a name" to evidence-cited copy, and document `draft_source` / `outcome`
  **Accept**: `grep -n "draft_source" README.md` returns a match; guarantee table mentions citation
- [ ] T050 [P] Update the constitution's Sync Impact Report — flip PRODUCT.md and README from ⚠ pending to ✅
  **Accept**: `grep -c "⚠" .specify/memory/constitution.md` returns 0 for the v5.0.0 block
- [ ] T051 Measure the real fallback rate before full rollout: run against a copy of the live 130-note vault and record the agent/template split
  **Accept**: run completes; `drafted by agent` ≥ 80% of email-channel non-frozen companies, else tune V3/V4 and re-measure before rolling out
- [ ] T052 Full suite green with `tests/unit/test_draft.py` **unmodified** — the mechanical proof of FR-316
  **Accept**: `git diff --exit-code tests/unit/test_draft.py && pytest tests/ -q`

---

## Dependencies

```
Phase 1 (Setup)
    │
    ├──► Phase 2 (US3 freeze) ──────────────┐   independent of the agent path
    │                                        │
    └──► Phase 3 (instructions) ──► Phase 4 (US1 agent) ──► Phase 5 (US2 fallback)
                    │                        │                       │
                    └────────────────────────┴──► Phase 6 (US4)      │
                                                                     │
         Phase 7 (US5 measurement) ─── independent, needs only Phase 1
                                                                     │
         Phase 8 (polish) ◄──────────────────────────────────────────┘
```

| Phase | Depends on | Notes |
|-------|-----------|-------|
| 1 Setup | — | |
| 2 US3 freeze | 1 | Touches only `vault.py` + `pipeline.py`; ship independently |
| 3 Instructions | 1 | Blocking prerequisite for US1 |
| 4 US1 agent | 1, 3 | The MVP |
| 5 US2 fallback | 4 | Completes the safety story |
| 6 US4 tuning | 3, 4 | Verification-only once 3 and 4 land |
| 7 US5 measurement | 1 | Fully independent; parallelizable with 3–6 |
| 8 Polish | all | Docs must reflect shipped behavior |

## Parallel Opportunities

- **T002–T004** — three independent dataclasses in `models.py`
- **T014–T017** — four instruction content files, no code dependency; can be written by a non-programmer while code proceeds
- **T011, T012** — two independent test modules
- **Phase 7 entirely** — measurement touches only `vault.py` frontmatter and the dashboard; can run alongside Phases 3–6
- **T048–T050** — three independent documentation files

## Implementation Strategy

**Ship in three increments:**

1. **Increment 1 — Safety (Phases 1–2).** Freeze guard only. Immediately
   deployable, protects 27 live sent notes, no behavior change to drafting. Ship
   this even if the rest slips.
2. **Increment 2 — MVP (Phases 3–5).** Agent path, validator, fallback,
   counting. This is the feature. Roll out with `--limit` before a full re-draft,
   and let T051's measured fallback rate gate the full run.
3. **Increment 3 — Completeness (Phases 6–8).** Tuning verification,
   measurement, documentation.

**Suggested MVP scope**: Phases 1, 2, 3, 4, 5. Phases 6–8 are valuable but do
not block honest personalized drafts reaching the vault.

**Rollback**: every increment is independently revertible. The template path is
never modified, so reverting `agent_draft.py`'s wiring in `pipeline.py` returns
the tool to today's exact behavior.
