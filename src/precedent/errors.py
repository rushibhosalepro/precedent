"""Every failure the engine reports, each with the exit code the CLI uses.

Agents are told: any non-zero exit means escalate to a person and stop. So a
failure is always loud and never reads as "approved".
"""


class PrecedentError(Exception):
    exit_code = 1
    kind = "error"


class SchemaError(PrecedentError):
    """Input or stored state does not fit the strict schema."""

    exit_code = 2
    kind = "schema"


class NotFound(PrecedentError):
    exit_code = 2
    kind = "not_found"


class Refused(PrecedentError):
    """A valid request the engine will not carry out: wrong role, stale state,
    an approval that does not verify, a rule that would add a conflict."""

    exit_code = 3
    kind = "refused"


class Tampered(PrecedentError):
    """State changed outside the engine. Nothing runs until a person looks."""

    exit_code = 4
    kind = "tampered"


class SwitchUnavailable(PrecedentError):
    exit_code = 5
    kind = "switch_unavailable"
