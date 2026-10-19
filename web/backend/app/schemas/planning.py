from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Finite = Annotated[float, Field(allow_inf_nan=False, ge=-1e9, le=1e9)]


class Vertex(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: Finite
    y: Finite


class PlanningObject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    type: Literal["RACK", "HOME", "PICKUP", "DELIVERY", "CHARGING", "NO_GO"]
    name: str = Field(min_length=1, max_length=120)
    x: Finite
    y: Finite
    yaw: Finite = 0
    width: Annotated[float, Field(gt=0, le=1e6, allow_inf_nan=False)] | None = None
    height: Annotated[float, Field(gt=0, le=1e6, allow_inf_nan=False)] | None = None
    # Polygon vertices are local metres, rotated by yaw around x/y.
    vertices: list[Vertex] = Field(default_factory=list, max_length=128)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Object name cannot be blank")
        return value.strip()

    @model_validator(mode="after")
    def geometry(self):
        if self.type == "RACK" and (self.width is None or self.height is None):
            raise ValueError("RACK requires width and height")
        if self.type == "NO_GO":
            if len(self.vertices) < 3:
                raise ValueError("NO_GO requires at least three vertices")
            points = [(p.x, p.y) for p in self.vertices]
            if len(set(points)) != len(points):
                raise ValueError("Polygon vertices must be distinct")
            area = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points, points[1:]+points[:1]))
            if abs(area) < 1e-9:
                raise ValueError("Polygon must have nonzero area")
            edges = list(zip(points, points[1:]+points[:1]))
            for i, (a,b) in enumerate(edges):
                for j in range(i+1, len(edges)):
                    if j == i+1 or (i == 0 and j == len(edges)-1):
                        continue
                    if intersects(a,b,*edges[j]):
                        raise ValueError("Polygon must not self-intersect")
        elif self.vertices:
            raise ValueError("Only NO_GO uses polygon vertices")
        if self.type != "RACK" and (self.width is not None or self.height is not None):
            raise ValueError("Only RACK uses width and height")
        return self


def intersects(a, b, c, d):
    def cross(p,q,r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def on(p,q,r):
        return min(p[0],q[0])-1e-9 <= r[0] <= max(p[0],q[0])+1e-9 and min(p[1],q[1])-1e-9 <= r[1] <= max(p[1],q[1])+1e-9
    v=[cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)]
    return (v[0]*v[1]<0 and v[2]*v[3]<0) or any(
        abs(n)<1e-9 and on(p,q,r)
        for n,p,q,r in [(v[0],a,b,c),(v[1],a,b,d),(v[2],c,d,a),(v[3],c,d,b)])


class PlanningSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    objects: list[PlanningObject] = Field(max_length=500)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({obj.id for obj in self.objects}) != len(self.objects):
            raise ValueError("Duplicate object IDs")
        return self
