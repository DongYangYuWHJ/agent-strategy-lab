# Fix Packaging dependency-group validation so malformed requirement strings are reported together with other errors from the group.

- Use the existing grouped-error contract for malformed dependency groups. An invalid requirement string must appear as an InvalidRequirement inside the ExceptionGroup, even when it is the only problem.
- Report all errors among the items of the malformed group, including malformed include objects and multiple invalid requirement strings. This applies to lookup, resolution, and a malformed group reached through otherwise valid includes.
- Preserve the order and duplicates of valid expanded requirements. Lookup must keep unresolved includes, and resolution must still detect cycles and missing groups.
- Keep public APIs and the existing error types. Do not modify the read-only app.py adapter.

Use the bundled Python source and standard library. Run the public checks during development.
