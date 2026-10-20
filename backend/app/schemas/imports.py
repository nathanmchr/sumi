from pydantic import BaseModel, Field


class ImportSummaryOut(BaseModel):
    item_type: str
    created: int = Field(default=0)
    updated: int = Field(default=0)
    skipped: int = Field(default=0)
    errors: list[str] = Field(default_factory=list)

