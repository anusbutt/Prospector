# Contract: Agent Drafting Request / Response / Validation

**Feature**: 006-agentic-drafting | **Date**: 2026-07-20
**Module**: `prospector/agent_draft.py`

One request per email-channel company per run. No retry, no repair call, no
judge model (FR-307, FR-311).

---

## 1. Entry point

```python
def draft_email(
    prospect: Prospect,
    settings: Settings,
    instructions: InstructionSet,
) -> Draft:
    """Agent path with automatic fallback. NEVER raises.

    Returns a Draft with source="agent" when the model path produced validated
    copy, otherwise the locked-template Draft with source="template" and the
    rejection reasons in validation_errors.
    """
```

**Guarantees**

| # | Guarantee |
|---|-----------|
| G1 | Never raises. Every failure path returns a usable Draft (FR-315, FR-318). |
| G2 | Issues at most one HTTP request (FR-307). |
| G3 | Issues **zero** requests when the evidence catalogue is empty (FR-317). |
| G4 | Is never called for messenger-channel companies (FR-308) or frozen notes (FR-326) — the pipeline guards both before this function. |

---

## 2. Request

`POST https://openrouter.ai/api/v1/chat/completions` — the existing endpoint,
headers, and auth from `draft.py`.

```json
{
  "model": "<settings.openrouter_model>",
  "temperature": 0.7,
  "response_format": {"type": "json_object"},
  "messages": [
    {"role": "system", "content": "<InstructionSet.text>"},
    {"role": "user",   "content": "<company payload, JSON>"}
  ]
}
```

Timeout 60s, matching the existing call.

### Company payload

```json
{
  "company": "Acme Duct Cleaning",
  "greeting": "Hi Scott,",
  "city": "Dallas",
  "evidence": [
    {
      "id": "about_page_1",
      "kind": "about_page",
      "value": "Scott Brenner",
      "source": "https://acmeduct.com/about",
      "excerpt": "Owner Scott Brenner founded Acme in 2003 ..."
    },
    {
      "id": "hook_source_1",
      "kind": "hook_source",
      "value": "22 years in business",
      "source": "https://acmeduct.com/about",
      "excerpt": "... serving the Dallas area for 22 years"
    }
  ],
  "offer_id": "offer"
}
```

**Constraints on the payload**

- `evidence` carries only extracted `Evidence` fields. Raw page HTML is never
  included (FR-302).
- `greeting` is already resolved by code; the model does not choose the name
  (research R3).
- No tools, functions, or tool_choice are sent. The model has no tool, network,
  or filesystem access (FR-303).

---

## 3. Response

```json
{
  "subject": "Free 10-day pilot for Acme Duct",
  "blocks": [
    {
      "text": "I saw Acme has been cleaning ducts around Dallas for 22 years — that is a long time to build a referral base.",
      "cites": ["hook_source_1"]
    },
    {
      "text": "I'm giving 5 duct-cleaning companies a free 10-day pilot of the Omniveer Duct Lead Qualifier. It answers new leads, qualifies them, and books appointments straight into your calendar.",
      "cites": ["offer"]
    },
    {
      "text": "You can see the short demo here:\nhttps://www.omniveer.com/duct-lead-qualifier",
      "cites": ["offer"]
    },
    {
      "text": "Reply if you'd like one of the five spots.",
      "cites": ["offer"]
    }
  ]
}
```

Code-fenced JSON is tolerated (the existing `_strip_code_fences` helper is
reused — some providers ignore `response_format`).

### Parse rejections

| Condition | Result |
|-----------|--------|
| Non-JSON, or JSON that is not an object | reject → fallback |
| `subject` missing or empty | reject → fallback |
| `blocks` missing, not a list, or count outside 3–6 | reject → fallback (FR-305) |
| A block is not an object, or lacks `text` / `cites` | reject → fallback (FR-304) |
| `cites` is not a list of strings | reject → fallback |

---

## 4. Assembly

Deterministic, in code (FR-306). The model's prose is never edited — only
accepted whole or rejected whole.

```
<greeting>          # from expected_greeting(prospect) — code, not model
                    # blank line
<block[0].text>
                    # blank line
<block[1].text>
...
                    # blank line
<SIGNATURE>         # existing constant "Anas\nFounder, Omniveer"
```

The subject is used verbatim from the response after validation.

---

## 5. Validation

Deterministic Python only. No model is consulted (FR-311). **All** checks run
so every reason is collected (FR-314); any failure rejects the whole draft.

### 5.1 Citation checks (new)

| Rule | Requirement |
|------|-------------|
| **V1** | Every block has ≥ 1 citation (FR-309). |
| **V2** | Every citation is either `"offer"` or an `EvidenceRef.id` built for **this** company **this** run (FR-310). |
| **V3** | An offer-only block (`cites == ["offer"]`) contains no prospect-specific token: company name or a distinctive token from it, resolved city, `name_used`, `name_candidate`, or hook value. Case-insensitive substring match. |
| **V4** | At least one block cites a non-`offer` evidence id — otherwise the draft is unpersonalized and the cheaper template is used instead. |

V3 is the anti-laundering rule (research R2): it stops the model from making a
prospect claim while citing only the offer.

V4 is an efficiency rule, not a safety rule: a draft that cites nothing but the
offer is template-equivalent, so the template answers and the model output is
discarded.

### 5.2 Retained checks (from `draft.py`, applied to the assembled body)

Per FR-312 and FR-313, unchanged in meaning:

| Rule | Requirement |
|------|-------------|
| **V5** | No banned advertising vocabulary (`AD_CLAIM_SUBSTRINGS`) in body or subject. |
| **V6** | `body.count("http") == 1` and that link is `PRODUCT_URL`. |
| **V7** | No `linkedin.com` anywhere in the body. |
| **V8** | Body ends with `SIGNATURE`. |
| **V9** | No unfilled `[slot]` markers in body or subject. |
| **V10** | Body starts with the expected greeting. |
| **V11** | If `name_used != "team"`, the greeting name traces to recorded evidence or the input `owner_name`. |
| **V12** | `subject` contains only tokens drawn from the company name. |

V5–V12 reuse the existing predicates in `draft.py`. They are applied to
model-written prose rather than template output, which is the whole point: the
checks that survive free prose keep working, and the citation rules replace the
one that does not (template-prose invariance).

---

## 6. Failure → fallback matrix

Every row returns a valid Draft. Nothing aborts the batch (FR-318).

| Failure | `source` | Recorded reason |
|---------|----------|-----------------|
| Empty evidence catalogue | `template` | `no evidence to cite` *(no request made)* |
| HTTP / transport error | `template` | `agent call failed: <exc>` |
| Non-JSON or malformed shape | `template` | `agent response malformed: <detail>` |
| Block count out of range | `template` | `agent returned N blocks (expected 3-6)` |
| Citation validation failure | `template` | each failing rule, e.g. `block 2 cites unknown id 'about_page_9'` |
| Retained-check failure | `template` | existing message text, e.g. `ad-running claim detected: 'advertis'` |

Reasons land in `Draft.validation_errors`, are written into the note's `## Draft`
region when the draft is a fallback, and are aggregated into
`RunSummary.fallback_reasons` for the CLI summary (FR-320).

---

## 7. Test obligations

| Contract element | Test |
|---|---|
| G1 never raises | Parametrized over every failure mode; assert a Draft returns |
| G2 one request | respx call count == 1 |
| G3 no request when evidence empty | respx call count == 0 |
| V1–V4 | Unit tests per rule, hand-built `Prospect` + stub response |
| V3 anti-laundering | Block citing only `offer` but containing the company name → rejected |
| V5–V12 | Existing `test_draft.py` predicates, re-exercised against agent output |
| Assembly | Golden-string test on a fixed stub response |
| FR-316 | `tests/unit/test_draft.py` passes **unmodified** |
