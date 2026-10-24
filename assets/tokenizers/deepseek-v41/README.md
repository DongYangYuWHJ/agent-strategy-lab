# DeepSeek V4.1 text input counting assets

Only tokenizer/template data is bundled here; no model weights or remote Python
code are downloaded or executed. The original MIT license is in `LICENSE`.

- `tokenizer.json`: DeepSeek's official recipe repository, revision
  `935817c66f5d6e64838f419692545f06787e485f`,
  `static/tokenizers/v41/tokenizer.json`.
  [Source](https://github.com/deepseek-ai/deepseek-recipe/blob/935817c66f5d6e64838f419692545f06787e485f/static/tokenizers/v41/README.md)
  SHA-256: `81f64d1248a68ce3663e07ab3ee48b851e5df0e32d27cb98e4c9a268151e8d99`.
- `chat_template.jinja`: DeepSeek's official `DeepSeek-V4.1-Flash` repository,
  revision `314113f8a7dadb388215396ba5fbee2c610a04d6`.
  [Source](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/314113f8a7dadb388215396ba5fbee2c610a04d6/chat_template.jinja)
  SHA-256: `d959d804d5101b79a49b6ff1bf3c54cd5affa9a5a78c503d925f3090040b31c3`.

The recipe tokenizer changes the image-token spelling; this counter explicitly
supports text/tool messages only. It includes the complete reasoning history,
tool definitions and tool results. Template rendering happens in a Jinja sandbox;
the outgoing API request is not changed by counting.

As verified on 2026-10-23, the API name `deepseek-flash` refers to
DeepSeek-V4.1-Flash-1017. This is a changing API alias, not a pinned server model:
recheck these assets when the provider updates its tokenizer or prompt format.
[API model mapping](https://api-docs.deepseek.com/quick_start/pricing/)

Counts are still validated against actual response usage, and admission adds a
configurable margin. They are not a contractual billing upper bound.
