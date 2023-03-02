from ninja import Schema
from typing import List, Optional


class ProjectSchema(Schema):
    id: int
    name: str
    description: str
    administrators: List[str]
    created_at: str
    updated_at: str
    project_type: str
    talk_markdown: str
    url: str


class ProjectPatchSchema(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    talk_markdown: Optional[str] = None


class TextClassificationOutSchema(ProjectSchema):
    categories: List[str]


class MachineTranslationOutSchema(ProjectSchema):
    pass


class ProjectEntryPatchSchema(ProjectSchema):
    classification: Optional[str] = None
    adequacy: Optional[float] = None
    fluency: Optional[float] = None


class EntrySchema(Schema):
    unannotated_source: int
    payload: dict
