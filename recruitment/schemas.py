from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Schema(BaseModel):
    model_config = ConfigDict(extra='forbid')

Level = Literal['strong','moderate','weak','mentioned','missing']
Category = Literal['skills','projects','experience','education','expectations']
class Ref(Schema):
    block_id: str
    exact_quote: str
class Requirement(Schema):
    label: str
    canonical_key: str
    category: Category
    essential: bool
    weight: int = Field(ge=1, le=5)
    minimum_months: int | None
    minimum_count: int | None
    jd_quote: str
class JobOutput(Schema):
    requirements: list[Requirement] = Field(min_length=1, max_length=15)
class Credential(Schema):
    description: str
    source_refs: list[Ref]
class Experience(Schema):
    id: str
    role: str
    organization: str | None
    start_date: str | None
    end_date: str | None
    date_precision: Literal['month','year','unknown']
    technologies: list[str]
    source_refs: list[Ref]
class Project(Schema):
    id: str
    title: str
    description: str
    technologies: list[str]
    source_refs: list[Ref]
class Links(Schema):
    github: str | None
    linkedin: str | None
    instagram: str | None
    reddit: str | None
    portfolio: str | None
class Candidate(Schema):
    name: str | None
    email: str | None
    phone: str | None
    education: list[Credential]
    skills: list[str]
    experience: list[Experience]
    projects: list[Project]
    achievements: list[str]
    certifications: list[Credential]
    supplied_links: Links
class Match(Schema):
    requirement_id: int
    relevance: Literal['direct','related','absent']
    evidence_level: Level
    source_refs: list[Ref]
    relevant_project_ids: list[str]
    relevant_experience_ids: list[str]
    explanation: str
class Claim(Schema):
    id: str
    text: str
    canonical_key: str | None
    source_refs: list[Ref]
    supporting_refs: list[Ref]
    support_level: Level
    claimed_months: int | None
    relevant_experience_ids: list[str]
    review_notes: list[str]
class ReviewFlag(Schema):
    claim_id: str
    type: Literal['conflicting_statements']
    claim_refs: list[Ref]
    evidence_refs: list[Ref]
    explanation: str
class ResumeOutput(Schema):
    candidate: Candidate
    requirement_matches: list[Match]
    claims: list[Claim] = Field(max_length=15)
    review_flags: list[ReviewFlag]
class Question(Schema):
    id: str
    scenario: str
    dimensions: list[str]
    rubric: str
class QuestionsOutput(Schema):
    questions: list[Question] = Field(min_length=3, max_length=3)
class Dimension(Schema):
    dimension: str
    level: Literal['Strong','Moderate','Limited','Insufficient evidence']
    rationale: str
class ResponseEvaluation(Schema):
    question_id: str
    dimensions: list[Dimension]
    answer_quotes: list[str]
    rationale: str
class EvaluationOutput(Schema):
    responses: list[ResponseEvaluation]
    summary: str
class FeedbackOutput(Schema):
    strengths: list[str]
    weaknesses: list[str]
    opportunities: list[str]
    role_challenges: list[str]
    improvement_steps: list[str]
    subject: str
    body: str
