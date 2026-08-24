"""Regression test for the costliest bug so far (24.08., three nights).

bt-agent.py declared its agent methods on org.bluez.AgentManager1 instead of
org.bluez.Agent1. Registration succeeded (that IS AgentManager1's job), but
every actual agent callback -- RequestConfirmation above all -- answered
UnknownMethod, which bluetoothd read as a rejection: AuthenticationFailed
within ~2 ms, no code on the display, no CONFIRM line in the journal.
Registration worked, reachability did not. This static check catches that
class of bug without a bus, without bluez, without the camera.
"""

import ast
import pathlib

AGENT = pathlib.Path(__file__).resolve().parents[1] / "tools" / "bt-agent.py"

AGENT1 = "org.bluez.Agent1"

#: every method the bluez Agent1 API may call on us
REQUIRED = {
    "Release",
    "RequestPinCode",
    "RequestPasskey",
    "DisplayPasskey",
    "DisplayPinCode",
    "RequestConfirmation",
    "RequestAuthorization",
    "AuthorizeService",
    "Cancel",
}


def decorated_methods(source: str) -> dict[str, str]:
    """Map method name -> dbus interface from @dbus.service.method decorators."""
    tree = ast.parse(source)
    out: dict[str, str] = {}
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef)):
            for dec in fn.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "method"
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                ):
                    out[fn.name] = str(dec.args[0].value)
    return out


def test_all_agent_methods_live_on_agent1():
    methods = decorated_methods(AGENT.read_text())
    assert methods, "no @dbus.service.method found -- parser broken?"
    bad = {name: iface for name, iface in methods.items() if iface != AGENT1}
    assert not bad, (
        f"methods not on {AGENT1}: {bad} -- bluetoothd would answer "
        "UnknownMethod again (the three-night bug)"
    )


def test_agent_implements_the_full_agent1_api():
    methods = decorated_methods(AGENT.read_text())
    missing = REQUIRED - set(methods)
    assert not missing, f"Agent1 methods missing: {missing}"
