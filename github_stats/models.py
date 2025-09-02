from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ClientState(BaseModel):
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    last_poll: Optional[datetime] = None
    poll_interval: int = 60