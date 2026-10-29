from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SearchArgs(Strict):
    query: str = Field(min_length=1, max_length=300)
    top_k: int = Field(default=5, ge=1, le=10)


class ReadArgs(Strict):
    doc_id: str = Field(min_length=1, max_length=80)


class Citation(Strict):
    doc_id: str
    version_date: str
    chunk_id: str
    quote: str = Field(min_length=1)


class Claim(Strict):
    text: str
    citation_indices: list[int] = Field(min_length=1)


class Conflict(Strict):
    topic: str
    explanation: str
    citation_indices: list[int] = Field(min_length=2)


class Answer(Strict):
    status: Literal['answered', 'needs_clarification', 'conflict_unresolved',
                    'insufficient_evidence', 'incomplete', 'failed']
    answer: str = Field(min_length=1)
    claims: list[Claim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    clarification: str | None = None
    stop_reason: str


class Decision(Strict):
    action: Literal['search_documents', 'read_document', 'ask_user', 'finish']
    reason: str = Field(min_length=1, max_length=300)
    arguments: dict = Field(default_factory=dict)
    result: Answer | None = None


class RunRequest(Strict):
    question: str = Field(min_length=1, max_length=3000)
    mode: Literal['live', 'mock'] = 'live'
    scenario: str = 'normal'
