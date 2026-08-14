from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeVersionSummary(BaseModel):
    """Metadata for one uploaded version.

    Deliberately excludes `pdf_bytes`. The profile screen lists versions on every
    visit, and returning megabytes of base64 there would make it slow for no benefit
    when the file is separately downloadable.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    filename: str
    byte_size: int
    is_active: bool
    uploaded_at: datetime
