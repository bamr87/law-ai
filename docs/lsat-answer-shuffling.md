# Per-attempt answer shuffling

BL-20260606-01. A bank question used to present its key in the same place forever: `lr-014`'s credited answer was `C` on the first attempt, on the tenth, and on the export a learner drilled offline. Position is then a cue, and a cue that has nothing to do with the reasoning is the wrong thing to learn — especially in a tool whose whole premise is repeated passes over a small bank.

So a serve may permute the choices. The permutation is per serve, not per question, and it is never stored.

## The platform: shuffle on the server, reverse with a signed token

`GET /api/lsat/questions?shuffle=1` (and `GET /api/lsat/questions/<id>?shuffle=1`) returns an ordinary question — choices labelled A-E top to bottom — plus a `remap` token. The token is `<order digits>.<signature>`, where the signature is an HMAC-SHA256 over `question_id:order` keyed on `SECRET_KEY`. Everything the grader needs to undo the shuffle rides in that string, so there is no session, no cache row, and nothing for two API servers to share but the key they already share.

`POST /api/lsat/grade` accepts the token as `remap`. Given one it:

1. verifies the signature, and returns **400** when it fails — a stale or forged token must not silently fall back to the stored order, which would mark a correct answer wrong;
2. maps the label the learner picked back to the stored one before comparing it to the key;
3. maps `correct_choice` forward, so the response names the letter that was on screen;
4. rewrites the explanation's label references through the same permutation.

The token is bound to its question id, so one minted for `lr-014` cannot be replayed against `lr-015` to move that item's key. Grading without a token still works exactly as before: shuffling is opt-in per serve, and an older client keeps functioning.

The audit trail records the **stored** label (`choice`) plus `shuffled: true`, so answer-distribution analysis measures the bank rather than the shuffle.

`GET /api/lsat/questions/<id>/guide?remap=<token>` applies the same rewrite to solve-guide steps: a hint that says "eliminate (B)" beside a shuffled board would contradict the screen.

`GET /api/lsat/passages/<id>?shuffle=1` takes the same parameter and mints a token per attached question. That endpoint matters more than its one line suggests: every Reading Comprehension and Logic Games item carries a `passage_id` and is served from there rather than from `/api/lsat/questions`, so it is the majority of the bank. It shipped unshuffled at first, which left the named defect alive on exactly the surface that serves most items; both platform panels now ask for the shuffle (`LrPanel` on the question endpoint, `PassagePanel` on this one) and both echo `remap` back through `QuestionCard` at grade time.

## The static export: shuffle in the browser

`lsat-static/` has no server — the bundle carries the key and grades client-side — so `lib/shuffle.ts` draws the permutation in the browser and nothing leaves it. That is the same trust model the export already had, applied to the same defect. The order is drawn once per question **per session**, so paging back through a section reviews the board you answered; a reload is a new attempt with a new order. What is written to `localStorage` is the stored label, so progress recorded today is still readable next week.

## Label references are remapped, not hoped about

The shipped banks are label-bound: explanations say "A is correct: …" and "(D) is the exception", and spec 045 guide steps do too. Under a permutation those sentences would contradict the screen, so `remap_labels` rewrites them — conservatively. It matches only the shapes a label reference actually takes:

- `(B)` — the exam's own parenthesised notation;
- `choice C`, `answer D`, `option E`;
- a bare label doing subject work, recognised by what follows it: `A is`, `B and C`, `D, not E`.

The "A" in "A recent study found the opposite" is left alone, which is the point of enumerating the shapes rather than replacing every capital letter. Every rewrite happens in a single pass over the string, so a permutation that swaps two labels cannot rewrite the same reference twice.

Both implementations — `backend/law_ai/lsat/services/shuffle.py` and `lsat-static/lib/shuffle.ts` — carry the same patterns, and both are tested against the shipped bank: the identity mapping must leave every explanation byte-identical, and a permutation followed by its inverse must return the original text.

## What is not covered yet

- The **AI tutor** prompt (`services/tutor.py`) and cross-check still speak in stored labels. A tutor answer during a shuffled attempt can therefore name a letter the learner is not looking at. Remapping the tutor's *output* is not enough — it reasons about the choices — so this wants the prompt to receive the displayed board, which is a larger change than the serve path.
- Bank content is still authored with bare labels. A future migration to `{{A}}`-style placeholders would make the remap a substitution rather than a rewrite; the conservative rewrite exists precisely so that migration is not a prerequisite.
