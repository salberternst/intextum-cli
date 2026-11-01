# Verifying values

Rules catch missing, invalid, and unsupported values, but not a confident
mistake, such as the sender extracted as the buyer. An optional decision model
checks each non-empty extracted field against the document and returns the
probability that the document states that value in that role. Fields below the
threshold get `unverified:<field>` and need review; the viewer shows the probability as
**Verified 97%** or **Doubtful 8%** on each field card.

The same request also checks automatic classifications, including unclassified
results: it gives a probability for every class and for "none of these". The
viewer shows **Class confirmed — 95%** or, for an unclassified document, **No
class fits — 97% sure**. When the current class (or "no class") is below the
threshold, the result gets `class_doubtful` and the viewer suggests the likelier
class, e.g. **Possibly Invoice — 62%** with a **Use Invoice** button; nothing
changes without that click. **Change class…** lists the probability next to
each class. Classes chosen in the viewer, in `groups.yaml`, or with `--class`
are deliberate and not checked.

## Configure the verifier

Verification only needs an endpoint. Set the model in `.env` (or with
`--verifier-model`):

```sh
INTEXTUM_VERIFIER_MODEL=your-decision-model
# INTEXTUM_VERIFIER_BASE_URL=http://localhost:11434
# INTEXTUM_VERIFIER_API_KEY=your-api-key
# INTEXTUM_VERIFIER_THRESHOLD=0.3
```

The server and model must support decision requests. A chat-completion endpoint
alone is insufficient for CLI verification.

| Endpoint | Route used by intextum |
| --- | --- |
| Ollama or llama.cpp server with decision support | `/v1/systemone` |
| OpenRouter | `/api/alpha/decisions` |

The route follows from the base URL: OpenRouter uses its decisions API,
everything else `/v1/systemone`. The extraction API key is sent only when the
verifier uses the extraction endpoint. See the
[settings reference](../configuration.md#settings-reference) for environment
variables, CLI overrides, and defaults.

## When verification runs

Verification runs after all groups are extracted. Model loading and memory
management belong to the endpoint server; intextum only sends requests.

New or re-extracted results are checked, and unchanged results reuse their
verification. Changing the verifier model, endpoint, or threshold reruns
verification without invalidating extraction. Viewer re-extraction also checks
the re-extracted groups. Pass `extract --no-verify` to skip verification for a run.

To verify an existing workspace without converting originals or extracting again:

```bash
intextum verify results.sqlite --verifier-model your-decision-model
intextum verify results.sqlite --verifier-model your-decision-model --force
```

These commands use cached document text. `--force` rechecks all eligible results,
including automatic unclassified results; failed and duplicate groups are skipped.
A failed verification request adds a `verification failed` warning without adding
verification review flags. Existing review reasons remain. A field correction
settles `unverified` for that field.

## Evaluate a verifier

Measure a model on the corpus before relying on its flags:

```bash
python corpus/decision_check.py /tmp/corpus-results.sqlite \
    --base-url http://localhost:11434 --model your-decision-model
```

It reports, per threshold, how many wrong values (the extraction's own errors
plus injected ones, such as another field's value from the same document) the
model flags, and how many correct values it flags by mistake.

See the [CLI reference](../reference/cli.md#verify) for standalone verification
options and [Development](../development.md#test-corpus) for the corpus workflow.
