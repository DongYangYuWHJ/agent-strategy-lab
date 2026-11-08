# Fix TOMLKit document editing so adding a top-level scalar after promoting a dotted key to a nested table preserves field scope on serialization.

- After parsing a document with dotted keys, adding a child table and then assigning a root scalar must serialize to valid TOML. Reparsing must keep the new scalar at the root and preserve the nested tables and their values.
- The behavior must also work with deeper dotted keys, more than one new scalar, and existing root scalars or regular tables.
- Keep the existing text and key order when appending a scalar to a document whose dotted keys still render inline. Preserve existing comments and values in unchanged lines.
- Keep the public parse/dumps and mapping APIs. Do not modify the read-only app.py adapter.

Use the bundled Python source and standard library. Run the public checks during development.
