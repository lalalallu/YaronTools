from dataclasses import dataclass, field
from typing import List


@dataclass
class Point:
    x: float
    y: float
    z: float
    normal_x: float
    normal_y: float
    normal_z: float
    curvature: float
    raw_line: str = ""
    field_count: int = 7


@dataclass
class Group:
    index: int
    points: List[Point]


@dataclass
class PCDDocument:
    headers: List[str]
    groups: List[Group]
    total_points: int
    field_count: int
    original_raw: bytes = b""
