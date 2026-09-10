from pydantic import BaseModel, ConfigDict


class OperatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operator_code: str
    full_name: str
    role: str
    is_active: bool
