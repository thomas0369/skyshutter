#!/usr/bin/env python3
"""Auto-confirming BlueZ pairing agent (DisplayYesNo) for the camera bond.

The camera's classic bond uses SSP numeric comparison: its display shows a
code that a HUMAN confirms with OK, and our side must confirm as well. A
NoInputNoOutput agent silently downgrades SSP to Just Works -- then no code
ever appears on the camera and the pairing dies in a ~25 s window (measured
23.08., FINDINGS "Nacht"). This agent registers as DisplayYesNo and
auto-confirms every request, so the only human step left is the OK on the
camera display.

    python3 tools/bt-agent.py

Runs under the system python3 (needs python3-dbus + python3-gi), not the venv.
"""

from __future__ import annotations

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

AGENT_PATH = "/skyshutter/agent"


class AutoConfirmAgent(dbus.service.Object):
    @dbus.service.method("org.bluez.AgentManager1", in_signature="", out_signature="")
    def Release(self) -> None:  # noqa: N802 (bluez API name)
        pass

    @dbus.service.method("org.bluez.AgentManager1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid) -> None:  # noqa: N802
        print(f"AuthorizeService {uuid} -> yes", flush=True)

    @dbus.service.method("org.bluez.AgentManager1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device) -> str:  # noqa: N802
        print("RequestPinCode -> 0000", flush=True)
        return "0000"

    @dbus.service.method("org.bluez.AgentManager1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device) -> int:  # noqa: N802
        print("RequestPasskey -> 0", flush=True)
        return 0

    @dbus.service.method("org.bluez.AgentManager1", in_signature="ou", out_signature="")
    def DisplayPasskey(self, device, passkey) -> None:  # noqa: N802
        print(f"DisplayPasskey {passkey}", flush=True)

    @dbus.service.method("org.bluez.AgentManager1", in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pin) -> None:  # noqa: N802
        print(f"DisplayPinCode {pin}", flush=True)

    @dbus.service.method("org.bluez.AgentManager1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey) -> None:  # noqa: N802
        print(f"CONFIRM passkey={passkey} -> yes", flush=True)

    @dbus.service.method("org.bluez.AgentManager1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device) -> None:  # noqa: N802
        print("RequestAuthorization -> yes", flush=True)

    @dbus.service.method("org.bluez.AgentManager1", in_signature="", out_signature="")
    def Cancel(self) -> None:  # noqa: N802
        print("Cancel", flush=True)


def main() -> None:
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    AutoConfirmAgent(bus, AGENT_PATH)
    mgr = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1")
    mgr.RegisterAgent(AGENT_PATH, "DisplayYesNo")
    mgr.RequestDefaultAgent(AGENT_PATH)
    print("AGENT_BEREIT (DisplayYesNo, auto-confirm)", flush=True)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
