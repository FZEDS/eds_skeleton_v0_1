from pydantic import BaseModel, Field

class CDIForm(BaseModel):
    entreprise: str = Field(...)
    salarie: str = Field(...)
    categorie: str = Field(..., description="non-cadre ou cadre")
    idcc: str | None = Field(None, description="ex. 1486 ou 1486-syntec")
    duree_essai_mois: int = Field(..., ge=0, description="Durée d'essai en mois")
