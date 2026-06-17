from dataclasses import dataclass


@dataclass
class ConfigEntry:
    key: str
    value: str
    comment: str = ""
    raw_line: str = ""
    line_number: int = 0
    is_section: bool = False
    is_empty: bool = False
    indent: str = ""
    separator: str = "="
    trailing: str = ""
    has_inline_comment: bool = False
