"""Auth stub -- CQ-014 not built yet (spec.md Decision).

`get_current_lo_stub` returns the fixed dev LO id from env `DEV_LO_ID`
(seeded in CQ-010) and does no real authentication. CQ-014 replaces this
dependency's *implementation* only; every route in `pricing.enrichment` and
`pricing.scenarios` depends on it, and their signatures/tests must not
change when that happens.
"""

import uuid

from app.core.config import get_settings
from app.core.errors import AuthenticationError


def get_current_lo_stub() -> uuid.UUID:
    dev_lo_id = get_settings().dev_lo_id
    if not dev_lo_id:
        raise AuthenticationError("DEV_LO_ID is not set.")
    return uuid.UUID(dev_lo_id)
