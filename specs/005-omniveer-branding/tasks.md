# Tasks: Omniveer Branding & Strategic Links

**Input**: Design documents from `/specs/005-omniveer-branding/`
**Prerequisites**: spec.md, plan.md (no research/data-model — content-only change)

- [ ] T201 Update PRODUCT.md first (governance): §7.5 product-fact wording, §8
  offer + link-strategy paragraph + all three templates (product URL as the
  single body link, low-pressure closing question, `Anas / Founder at
  Omniveer` signature), §10 product name. Acceptance: §8 shows the new
  templates; no Nestaro in current-state text.
- [ ] T202 PATCH the constitution to v4.0.1: Principle V product-name
  reference (rule unchanged) + Sync Impact Report + footer. Acceptance:
  footer reads 4.0.1.
- [ ] T203 Rebrand `lead_qualifier_feature.md` (title + body product names).
  Acceptance: no Nestaro in the file.
- [ ] T204 Rebrand `prospector/draft.py`: SIGNATURE, offer paragraph, FB /
  agnostic / DM templates, invariant tuples, comments. Acceptance: golden
  drafts render the new prose; `grep -i nestaro prospector/` empty.
- [ ] T205 Add link-safety rules to the draft validators: exactly one `http`
  occurrence and it is the product URL (email body and DM); any
  `linkedin.com` in a body fails. Acceptance: crafted violations fail
  validation in tests.
- [ ] T206 Update `tests/unit/test_draft.py` golden strings + add tests:
  product page present exactly once; homepage absent; no LinkedIn in body;
  a second-link/LinkedIn injection is rejected; signature + closing question
  locked. Update `tests/integration/test_batch_run.py` and
  `test_success_criteria.py` golden strings. Acceptance: suite green.
- [ ] T207 Sweep remaining old references: `grep -ri "nestaro\|iamanusbutt\|anus-yousuf\|nestaroassistant"`
  over prospector/, tests/, README.md, PRODUCT.md current text, .env.example.
  Acceptance: only historical records (constitution sync history, old specs,
  PHRs) remain.
- [ ] T208 Run the complete test suite + compileall; fix every failure caused
  by the change; record changed files. Acceptance: pytest exits 0.
- [ ] T209 PHR under history/prompts/005-omniveer-branding/. Acceptance: file
  exists, prompt verbatim.
