from typing import List

from models.pcd_model import Point, Group, PCDDocument


def parse_pcd(text: str) -> PCDDocument:
    lines = text.splitlines()

    data_ascii_index = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("DATA"):
            data_ascii_index = i
            break

    if data_ascii_index == -1:
        raise ValueError("未找到 DATA ascii 标记行")

    headers = lines[: data_ascii_index + 1]
    data_lines = lines[data_ascii_index + 1:]

    total_points = 0
    field_count = 0
    for line in headers:
        stripped = line.strip()
        if stripped.startswith("POINTS"):
            total_points = int(stripped.split()[-1])
        elif stripped.startswith("FIELDS"):
            field_count = len(stripped.split()) - 1

    if total_points == 0:
        raise ValueError("无法从头部解析 POINTS 数量")

    points: List[Point] = []
    for line in data_lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < field_count:
            continue

        x = float(parts[0])
        y = float(parts[1])
        z = float(parts[2])

        nx, ny, nz, curv = 0.0, 0.0, 0.0, 0.0
        if len(parts) >= 4:
            nx = float(parts[3]) if len(parts) > 3 else 0.0
        if len(parts) >= 5:
            ny = float(parts[4]) if len(parts) > 4 else 0.0
        if len(parts) >= 6:
            nz = float(parts[5]) if len(parts) > 5 else 0.0
        if len(parts) >= 7:
            curv = float(parts[6]) if len(parts) > 6 else 0.0

        point = Point(
            x=x, y=y, z=z,
            normal_x=nx, normal_y=ny, normal_z=nz,
            curvature=curv,
            raw_line=line,
            field_count=field_count,
        )
        points.append(point)

    if len(points) < total_points:
        raise ValueError(
            f"实际数据行数 ({len(points)}) 少于头部声明的 POINTS ({total_points})"
        )

    groups = _build_groups(points)

    return PCDDocument(
        headers=headers,
        groups=groups,
        total_points=total_points,
        field_count=field_count,
    )


def _build_groups(points: List[Point]) -> List[Group]:
    groups = []
    group_size = 4
    for i in range(0, len(points), group_size):
        chunk = points[i: i + group_size]
        groups.append(Group(index=len(groups), points=chunk))
    return groups


def groups_to_text(document: PCDDocument) -> str:
    lines: List[str] = []

    for header_line in document.headers:
        lines.append(header_line)

    for group in document.groups:
        for point in group.points:
            if document.field_count == 7:
                lines.append(
                    f"{_format_value(point.x, point.raw_line, 0)} "
                    f"{_format_value(point.y, point.raw_line, 1)} "
                    f"{_format_value(point.z, point.raw_line, 2)} "
                    f"{_format_value(point.normal_x, point.raw_line, 3)} "
                    f"{_format_value(point.normal_y, point.raw_line, 4)} "
                    f"{_format_value(point.normal_z, point.raw_line, 5)} "
                    f"{_format_value(point.curvature, point.raw_line, 6)}"
                )
            else:
                parts = point.raw_line.split()
                if len(parts) >= 3:
                    parts[0] = _format_value(point.x, point.raw_line, 0)
                    parts[1] = _format_value(point.y, point.raw_line, 1)
                    parts[2] = _format_value(point.z, point.raw_line, 2)
                lines.append(" ".join(parts))

    return "\n".join(lines) + "\n"


def _format_value(value: float, raw_line: str, field_index: int) -> str:
    if not raw_line:
        return str(value)

    parts = raw_line.split()
    if field_index >= len(parts):
        return str(value)

    original_str = parts[field_index]

    if "." not in original_str and "e" not in original_str.lower():
        if value == int(value):
            return str(int(value))
        return _format_float_precision(value, original_str)

    if "." in original_str:
        clean = original_str.rstrip()
        if "." in clean:
            decimal_places = len(clean.split(".")[1])
            return f"{value:.{decimal_places}f}"

    return str(value)


def _format_float_precision(value: float, original: str) -> str:
    if "." in original:
        decimal_places = len(original.split(".")[1])
        return f"{value:.{decimal_places}f}"
    return str(value)
