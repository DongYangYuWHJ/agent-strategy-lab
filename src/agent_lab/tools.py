"""A shared tool vocabulary across every provider and execution strategy."""


def definition(name, description, properties):
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": list(properties), "additionalProperties": False}}


TOOLS = [
    definition("list_files", "List the task's readable source files.", {}),
    definition("read_file", "Read a source file; output is capped at 12000 characters.", {"path": {"type": "string"}}),
    definition("search", "Search source text for a literal string (up to 40 matches).", {"query": {"type": "string"}}),
    definition("write_file", "Replace an editable file with complete UTF-8 text. Other files are read-only.",
               {"path": {"type": "string"}, "content": {"type": "string"}}),
    definition("run_checks", "Run the operator-defined public checks and return recorded results.", {}),
    definition("submit", "Submit the completed changes for public verification and final acceptance. Call alone.",
               {"summary": {"type": "string"}}),
]


def validate_call(call):
    tool = next((item for item in TOOLS if item["name"] == call.name), None)
    if tool is None:
        raise ValueError("Unknown tool")
    properties = tool["parameters"]["properties"]
    if not isinstance(call.arguments, dict) or set(call.arguments) != set(properties):
        raise ValueError("Tool arguments do not match its schema")
    if any(not isinstance(value, str) for value in call.arguments.values()):
        raise ValueError("Tool arguments must be strings")


def execute(call, workspace, checks, remaining):
    validate_call(call)
    if call.name == "list_files":
        return {"ok": True, "files": workspace.list_files()}
    if call.name == "read_file":
        return {"ok": True, **workspace.read_file(**call.arguments)}
    if call.name == "write_file":
        return {"ok": True, **workspace.write_file(**call.arguments)}
    if call.name == "search":
        return {"ok": True, **workspace.search(**call.arguments)}
    if call.name == "run_checks":
        return checks.run("public", remaining)
    raise ValueError("Submission is handled by the coordinator")
