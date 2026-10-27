"""Fail-closed permission checks for the pinned OpenCode experiment roles.

V2 permission rules use last-match precedence, with agent rules appended after
global rules. Require a universal reset followed only by our exact grants, then
ask OpenCode itself to evaluate representative native/MCP/delegation actions.
"""
from .workflow_gateway import role_tool_definitions

ROLE_AGENT_IDS = {"solo": "lab-experiment-solo", "planner": "lab-experiment-planner",
                  "worker": "lab-experiment-executor"}
PERMISSION_POLICY_VERSION = "explicit-role-whitelist-v1"


class PermissionConfigurationError(ValueError):
    pass


def role_ids(strategy):
    if strategy == "single_agent":
        return {"solo": ROLE_AGENT_IDS["solo"]}
    if strategy == "planner_worker":
        return {role: ROLE_AGENT_IDS[role] for role in ("planner", "worker")}
    raise ValueError("Unsupported workflow strategy")


def role_permissions(role):
    rules = [{"action": "*", "resource": "*", "effect": "deny"}]
    rules.extend({"action": f"lab_{role}_{tool['name']}", "resource": "*", "effect": "allow"}
                 for tool in role_tool_definitions(role))
    if role == "planner":
        rules.append({"action": "subagent", "resource": ROLE_AGENT_IDS["worker"], "effect": "allow"})
    return rules


def audit_registered_agents(agents, expected):
    checked = []
    for role, name in expected["roles"].items():
        matches = [agent for agent in agents if agent.get("id") == name]
        if len(matches) != 1:
            raise PermissionConfigurationError(f"Experiment role missing or duplicated: {name}")
        actual = matches[0]
        config = expected["agents"][name]
        provider, model = config["model"].split("/", 1)
        ref = actual.get("model") or {}
        if (actual.get("mode") != config["mode"] or ref.get("providerID") != provider
                or ref.get("id") != model or ref.get("variant") not in (None, "default")):
            raise PermissionConfigurationError(f"Experiment role mode/model overridden: {name}")
        if actual.get("system") != config["system"]:
            raise PermissionConfigurationError(f"Experiment role instructions overridden: {name}")
        rules = actual.get("permissions")
        if not isinstance(rules, list):
            raise PermissionConfigurationError(f"Missing effective permission rules: {name}")
        resets = [i for i, rule in enumerate(rules)
                  if rule == {"action": "*", "resource": "*", "effect": "deny"}]
        if not resets:
            raise PermissionConfigurationError(f"No universal role deny boundary: {name}")
        tail = rules[resets[-1] + 1:]
        grants = {(r["action"], r["resource"]) for r in role_permissions(role) if r["effect"] == "allow"}
        found = set()
        for rule in tail:
            if (not isinstance(rule, dict) or set(rule) != {"action", "resource", "effect"}
                    or not all(isinstance(v, str) for v in rule.values())
                    or rule["effect"] not in {"allow", "deny", "ask"}):
                raise PermissionConfigurationError(f"Unrecognized permission rule after deny boundary: {name}")
            if rule["effect"] != "deny":
                key = (rule["action"], rule["resource"])
                if rule["effect"] != "allow" or key not in grants:
                    raise PermissionConfigurationError(f"Unexpected effective permission grant: {name}: {rule['action']}")
                found.add(key)
        if found != grants:
            raise PermissionConfigurationError(f"Required permission grant missing: {name}")
        checked.append({"role": role, "agent": name, "model": ref,
                        "deny_boundary_index": resets[-1], "allowlisted_grants": sorted(grants)})
    return checked


def permission_probes(role):
    probes = [{"action": action, "resources": [resource], "expected": "deny"}
              for action, resource in (("edit", "solution.py"), ("edit", "opencode.jsonc"),
                  ("edit", "../checks/final.py"), ("read", "solution.py"),
                  ("shell", "python solution.py"), ("glob", "*"), ("grep", "*"),
                  ("execute", "*"), ("question", "*"), ("websearch", "test"),
                  ("external_directory", "../*"), ("subagent", "lab-worker"),
                  ("subagent", "general"), ("subagent", ROLE_AGENT_IDS["planner"]))]
    for other in ("solo", "planner", "worker"):
        if other != role:
            probes.append({"action": f"lab_{other}_write_file", "resources": ["*"], "expected": "deny"})
    if role == "planner":
        probes.append({"action": "lab_planner_write_file", "resources": ["*"], "expected": "deny"})
    probes.append({"action": "subagent", "resources": [ROLE_AGENT_IDS["worker"]],
                   "expected": "allow" if role == "planner" else "deny"})
    probes.extend({"action": f"lab_{role}_{tool['name']}", "resources": ["*"], "expected": "allow"}
                  for tool in role_tool_definitions(role))
    return probes
