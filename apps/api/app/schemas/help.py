from pydantic import BaseModel, Field


class HelpCitation(BaseModel):
    document: str
    title: str
    heading_path: str
    excerpt: str


class HelpConversationTurn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=1, max_length=4000)


class HelpAskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    history: list[HelpConversationTurn] = Field(default_factory=list, max_length=6)


class HelpAnswer(BaseModel):
    answer: str
    citations: list[HelpCitation]
    used_ai: bool
    role_keys: list[str]


class HelpOverview(BaseModel):
    title: str
    description: str
    suggested_questions: list[str]
    available_documents: list[str]
    role_keys: list[str]
