import re
from typing import List

from models.config_entry import ConfigEntry


class ConfigParser:
    @staticmethod
    def parse(content: str) -> List[ConfigEntry]:
        entries = []
        for i, line in enumerate(content.split('\n'), 1):
            original_line = line
            indent_match = re.match(r'^(\s*)', line)
            indent = indent_match.group(1) if indent_match else ""
            stripped = line.strip()

            if not stripped:
                entries.append(ConfigEntry(
                    "", "", raw_line=original_line, line_number=i,
                    is_empty=True, indent=indent
                ))
                continue

            if stripped.startswith('#'):
                entries.append(ConfigEntry(
                    "", "", comment=stripped, raw_line=original_line,
                    line_number=i, indent=indent
                ))
                continue

            if stripped.startswith('[') and stripped.endswith(']'):
                entries.append(ConfigEntry(
                    stripped[1:-1], "", raw_line=original_line,
                    line_number=i, is_section=True, indent=indent
                ))
                continue

            match = re.match(r'^([^=:\s]+)(\s*[=:\s])(.*)$', stripped)
            if match:
                key = match.group(1).strip()
                separator = match.group(2)
                value_part = match.group(3)

                comment = ""
                value = value_part
                in_quote = False
                quote_char = None
                hash_pos = -1
                for idx, ch in enumerate(value_part):
                    if ch in '"\'':
                        if not in_quote:
                            in_quote = True
                            quote_char = ch
                        elif ch == quote_char:
                            in_quote = False
                            quote_char = None
                    elif ch == '#' and not in_quote:
                        hash_pos = idx
                        break

                if hash_pos >= 0:
                    value = value_part[:hash_pos].rstrip()
                    comment = value_part[hash_pos:].strip()

                entries.append(ConfigEntry(
                    key=key,
                    value=value,
                    comment=comment,
                    raw_line=original_line,
                    line_number=i,
                    indent=indent,
                    separator=separator,
                    has_inline_comment=bool(comment)
                ))
            else:
                entries.append(ConfigEntry(
                    "", "", comment=stripped, raw_line=original_line,
                    line_number=i, indent=indent
                ))

        return entries

    @staticmethod
    def generate(entries: List[ConfigEntry]) -> str:
        lines = []
        for e in entries:
            if e.is_empty:
                lines.append(e.raw_line)
            elif e.is_section:
                lines.append(e.raw_line)
            elif e.comment and not e.key:
                if e.indent:
                    lines.append(f"{e.indent}{e.comment}")
                else:
                    lines.append(e.comment)
            elif e.key:
                if e.value == "" and e.raw_line.strip().endswith(e.separator.strip()):
                    lines.append(e.raw_line)
                else:
                    line = f"{e.indent}{e.key}{e.separator}{e.value}"
                    if e.comment:
                        if e.has_inline_comment:
                            line += f" {e.comment}"
                        else:
                            line += e.comment
                    lines.append(line)
            else:
                lines.append(e.raw_line)

        return '\n'.join(lines)
