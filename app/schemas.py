# app/schemas.py
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

# --- Tolérance aux champs supplémentaires (Pydantic v1/v2) ---
try:
    # Pydantic v2
    from pydantic import ConfigDict
    class _EDSBase(BaseModel):
        model_config = ConfigDict(extra='allow')  # accepte des clés non déclarées
except Exception:
    # Pydantic v1
    class _EDSBase(BaseModel):
        class Config:
            extra = 'allow'

# Remplace BaseModel par notre base tolérante pour toutes les classes ci‑dessous
BaseModel = _EDSBase

class RuleMeta(BaseModel):
    source: Optional[str] = None
    source_ref: Optional[str] = None
    bloc: Optional[str] = None
    url: Optional[str] = None
    effective: Optional[str] = None

class ExplainItem(BaseModel):
    slot: Optional[str] = None
    kind: Optional[str] = "info"
    text: str
    ref: Optional[str] = None
    url: Optional[str] = None

class SuggestItem(BaseModel):
    field: str
    value: Any

# ---- Temps de travail
class WorktimeBounds(BaseModel):
    weekly_hours_min: Optional[float] = None
    weekly_hours_max: Optional[float] = None
    average_12_weeks_max: Optional[float] = None
    days_per_year_max: Optional[int] = None

class WorktimeCapabilities(BaseModel):
    work_time_modes: Dict[str, bool] = Field(default_factory=dict)
    defaults: Dict[str, Any] = Field(default_factory=dict)

class WorktimeResponse(BaseModel):
    bounds: WorktimeBounds = WorktimeBounds()
    rule: Optional[RuleMeta] = None
    capabilities: WorktimeCapabilities = WorktimeCapabilities()
    explain: List[ExplainItem] = Field(default_factory=list)
    suggest: List[SuggestItem] = Field(default_factory=list)

# ---- Salaire
class SalaryMinima(BaseModel):
    monthly_min_eur: Optional[float] = None
    base_min_eur: Optional[float] = None
    applied: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)

class SalaryResponse(BaseModel):
    minima: SalaryMinima = SalaryMinima()
    rule: Optional[RuleMeta] = None
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    explain: List[ExplainItem] = Field(default_factory=list)
    suggest: List[SuggestItem] = Field(default_factory=list)

# ---- Essai
class ProbationBounds(BaseModel):
    max_months: Optional[float] = None
    max_total_months: Optional[float] = None
    renewals_allowed: Optional[int] = None

class EssaiResponse(BaseModel):
    bounds: ProbationBounds = ProbationBounds()
    rule: Optional[RuleMeta] = None
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    explain: List[ExplainItem] = Field(default_factory=list)
    suggest: List[SuggestItem] = Field(default_factory=list)

# ---- Préavis
class Notice(BaseModel):
    demission: Optional[float] = None
    licenciement: Optional[float] = None

class PreavisResponse(BaseModel):
    notice: Notice = Notice()
    rule: Optional[RuleMeta] = None
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    explain: List[ExplainItem] = Field(default_factory=list)
    suggest: List[SuggestItem] = Field(default_factory=list)

# ---- Congés
class CongesPayload(BaseModel):
    min_days: Optional[int] = None
    suggested_days: Optional[int] = None

class CongesResponse(BaseModel):
    conges: CongesPayload = CongesPayload()
    rule: Optional[RuleMeta] = None
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    explain: List[ExplainItem] = Field(default_factory=list)
    suggest: List[SuggestItem] = Field(default_factory=list)
