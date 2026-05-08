"""Feature flag façade (workflow 32 / v2.5 T0.1).

Public API:
    flag(name)               -> bool — is the flag on?
    flag_value(name, default) -> T   — typed scalar flag value
    with_flag(name)           -> async context manager that asserts the flag is on
    register(name, ...)       -> declare a flag (registry; documents owner/added_in)
    list_flags()              -> snapshot of every registered flag + its current value
    set_for_test(name, value) -> override for unit tests; reverts on reset_for_test()
    reset_for_test()          -> drop all test overrides

Backed by a YAML file (default `/srv/iic/featureflags/flags.yaml`,
overridable with `IIC_FEATUREFLAGS_PATH`). The file is hot-reloaded
on every read whose mtime has changed; no inotify dependency in the
hot path so this stays portable across Linux + macOS dev hosts.
"""

from .core import (
    FlagSpec,
    flag,
    flag_value,
    list_flags,
    register,
    reset_for_test,
    set_for_test,
    with_flag,
)

__all__ = [
    "FlagSpec",
    "flag",
    "flag_value",
    "list_flags",
    "register",
    "reset_for_test",
    "set_for_test",
    "with_flag",
]
