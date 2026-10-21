# Doc Review

Track source changes that need human review in Git-managed Markdown translations. Doc Review does not translate text or claim to judge whether two languages mean the same thing. It records the exact source and translation files a reviewer approved, then shows what changed since that review.

## Quick start

Requires Python 3.8 or newer. Clone the repository, then install it:

```sh
git clone https://github.com/hahaha678/doc-review.git
cd doc-review
python -m pip install -e .
cd example
doc-review scan --format markdown
```

The example initially needs review. Record the initial review:

```sh
doc-review ack intro --reviewer "Your name" --reason "Compared the English and Chinese introduction"
doc-review scan --fail-on-review
```

Edit `example/docs/intro.md`, then run `doc-review scan` again. It will show `source_changed` and identify the source heading to inspect. After updating or checking the translation, record the decision:

```sh
doc-review ack intro --reviewer "Your name" --reason "Updated the installation paragraph"
```

Use a reason such as `Checked source wording change; translation still accurate` when no translation edit is needed. Commit `.doc-review/state.json` with the reviewed documents so the audit record is visible in a pull request.

## Configure a repository

Put a `doc-review.json` in the repository root:

```json
{
  "version": 1,
  "state": ".doc-review/state.json",
  "pairs": [
    {
      "id": "intro",
      "source": "docs/intro.md",
      "translation": "docs/intro.zh.md"
    }
  ]
}
```

Paths are relative to the config file, and each pair needs a stable, unique ID. Add each document pair explicitly. This avoids guessing from filenames and makes renamed or removed documents visible as work to review. The tool reads only configured Markdown pairs.

Commands:

```sh
doc-review scan --config doc-review.json
doc-review scan --config doc-review.json --format markdown --output translation-review.md
doc-review scan --config doc-review.json --format json --output translation-review.json
doc-review scan --config doc-review.json --fail-on-review
doc-review ack intro --config doc-review.json --reviewer "Li" --reason "Reviewed changed install steps"
```

`scan` is read-only. `ack` updates only the configured state file and requires a reviewer and reason. `--fail-on-review` returns exit code 2 when a pair needs review; invalid input returns 1. This project's [GitHub Actions workflow](.github/workflows/doc-review.yml) runs the tests and example. For your documentation repository, add a CI step running `doc-review scan --config doc-review.json --fail-on-review` after installing the package.

## Status meanings

| Status | Meaning |
| --- | --- |
| `unreviewed` | No review exists, or a path changed since the last review. |
| `source_changed` | The source changed since approval; inspect and update or confirm the translation. |
| `translation_changed` | The translation changed after approval; record a new review. |
| `both_changed` | Both files changed after approval. |
| `missing_source`, `missing_translation` | A configured file is absent. |
| `current` | Both files exactly match the last approved versions. |

The Markdown and JSON reports include a source diff and list headings affected by source edits. Headings are navigation hints derived from a line diff, not automatic semantic matching. A code-fence count difference is another review clue, not a failed translation test. The state file stores the last reviewed source text for these diffs; it is intended for documentation already committed to the same repository.

## Recommended review flow

1. Run `scan` in CI. A new pair starts as `unreviewed`.
2. A person compares the changed source with the existing translation, edits the translation if needed, and checks links and code examples.
3. That person runs `ack` for the specific pair and commits the updated state. Review the state-file diff in the pull request.
4. CI runs `scan --fail-on-review` again.

`ack` records a human statement. The tool cannot verify that a person actually read the document or that the translation is correct. Do not use it to approve every pair in bulk. If a pair is deleted from the config, it is no longer scanned; review config changes as part of the pull request.

## Development

```sh
python -m unittest discover -s tests -v
```

The implementation uses only Python's standard library. It runs locally without an AI service, API key, or network connection.

## License

MIT. See [LICENSE](LICENSE).
