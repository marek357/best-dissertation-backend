from typing import Optional
from ninja import Schema


class PrivateAnnotatorEntryCreateSchema(Schema):
    unannotated_source: int
    payload: dict


class PrivateAnnotatorEntryPatchSchema(Schema):
    category_name: Optional[str] = None
    fluency: Optional[float] = None
    adequacy: Optional[float] = None
