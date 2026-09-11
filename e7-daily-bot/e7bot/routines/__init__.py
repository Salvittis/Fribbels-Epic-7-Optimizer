"""Importing this package registers all routines into ROUTINE_REGISTRY."""
# Each module uses @register('name') for the side-effect of registration.

from . import login           # noqa: F401
from . import sanctuary       # noqa: F401
from . import guild           # noqa: F401
from . import hunt            # noqa: F401
from . import worldboss       # noqa: F401
from . import shop            # noqa: F401
from . import labyrinth_shop  # noqa: F401
