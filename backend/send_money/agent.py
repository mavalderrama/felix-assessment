"""Module-level root_agent for ADK CLI compatibility (adk run / adk web).

When ADK's CLI loads this module it looks for a module-level `root_agent`
attribute.  The Container boots Django and wires all dependencies.
"""

from __future__ import annotations

from send_money.infrastructure.container import Container

_container = Container()
root_agent = _container.create_agent()
