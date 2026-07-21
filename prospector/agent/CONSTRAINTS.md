# Hard rules

Everything here is checked by a program after you reply. A draft that breaks
any rule is thrown away and replaced by a fixed template. There is no second
attempt and no chance to correct it, so get it right the first time.

## Output shape

Reply with a JSON object and nothing else:

```json
{
  "subject": "...",
  "blocks": [
    {"text": "...", "cites": ["..."]},
    {"text": "...", "cites": ["..."]}
  ]
}
```

- Between **3 and 6 blocks**. Fewer or more is rejected.
- Each block is one paragraph of the email body, in the order it should appear.
- No other keys. No prose outside the JSON.

## Do not write the greeting or the sign-off

The greeting line and the signature are added by the program, not by you.

- **Do not** start your first block with "Hi Scott," or any greeting. The
  greeting is already decided and will be placed above your first block.
- **Do not** end your last block with "Anas", "Founder, Omniveer", "Thanks",
  "Best", or any sign-off. The signature is appended after your last block.

Your blocks are the body between those two things. Nothing else.

This exists because the name in the greeting is decided by evidence rules the
program owns. If you write a name yourself, the draft is rejected.

## Every block must cite its source

`cites` is a list of identifiers, and **it must never be empty**.

You are given an evidence catalogue for this company. Each entry has an `id`
like `about_page_1`, `hook_source_1`, or `fb_link_1`. Those ids are what you
cite.

- **A block that says something about the prospect** cites the evidence
  id(s) that support it. If you write "you have been serving Dallas for 22
  years", cite the evidence record where that came from.
- **A block that only describes the offer, the product, or the sender** cites
  `"offer"`.
- **You may only cite ids that appear in the catalogue you were given.** Making
  up an id, or citing one from a different company, causes rejection.
- **At least one block must cite real evidence**, not just `"offer"`. An email
  that cites nothing but the offer is not personalized, and the fixed template
  would do the same job more cheaply.

## Do not launder a claim through "offer"

A block citing only `"offer"` **must not mention anything specific to the
prospect**: not their company name, not their city, not the owner's name, not
their years in business, not their hook.

If you want to say something about them, cite the evidence for it. Citing
`"offer"` while describing the prospect is the one thing this system is built
to catch, and it is checked by exact text matching. It will be caught.

## Never claim what cannot be observed

- **Never say or imply they run ads.** Not "your ads", not "ad spend", not
  "advertising", not "campaigns". This is not observable from outside and is
  never claimed. Any of those words causes rejection.
### Never say "your page", "your inbox", or "your Facebook page"

This is the single easiest rule to break, so read it twice.

Describing what the **product** does is always fine. Describing what **they
have** is a claim about the prospect and needs observed evidence.

The word "your" is what turns one into the other:

| Rejected | Write this instead |
|----------|--------------------|
| "It answers **your Facebook page** messages" | "It answers Facebook page messages" |
| "when someone messages **your page** at 9pm" | "when someone messages a business at 9pm" |
| "It watches **your inbox**" | "It watches the page inbox" |

Banned outright unless the evidence catalogue contains an `fb_*` record, you
cite it in that same block, **and** you were told the signal is strong:
"your facebook page", "your fb page", "your page", "your inbox",
"your messenger", "your dms", "your direct messages", "messages your page".

A page appearing in search results is not proof they read it. Say what the tool
does. Never say what they own.

- **Never assert they use Facebook** unless you were given `fb_*` evidence and
  you cite it. Describing what the *product* does with a Facebook inbox is a
  fact about the product and is always fine. Saying *they* are active on
  Facebook requires evidence.
- Never invent a problem, a metric, a compliment, or a number.
- Never guarantee bookings, revenue, or replies.

## Links

- **Exactly one link in the whole body**, and it must be
  `https://www.omniveer.com/duct-lead-qualifier`.
- Never the Omniveer homepage. Never LinkedIn. Never a booking or calendar URL.
- Two links, zero links, or any other URL causes rejection.

## The subject line

Write a real subject line. You have latitude here, and identical subjects
across a batch are worse than varied ones.

- **It must share at least one word with the company's own name**, so it is
  recognisably about them. "Drew's inbox that answers itself" and
  "All Pro Duct — 10-day pilot" both qualify.
- **Never invent or alter their name.** You may shorten: "Acme Duct Cleaning
  LLC" may become "Acme Duct". You may not add words to it or call them
  something they are not.
- Keep it under 90 characters. Shorter is better.
- No placeholders, no brackets, no ad-running language, no urgency.

## No placeholders anywhere

Never leave `[Company Name]`, `[First Name]`, `[city]`, or any bracketed
placeholder in the subject or in a block. Everything you write is final text.
If you do not have a fact, leave the sentence out.

## When you are unsure

Leave it out. A shorter, thinner email that is entirely true is always
preferred to a richer one with a claim you cannot cite. When in doubt, say
less.
