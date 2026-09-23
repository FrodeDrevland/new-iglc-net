"""Read tables from a SQL Server .bacpac export without SQL Server.

A .bacpac is a zip file. model.xml describes the tables; Data/<schema>.<table>/*.BCP
hold the rows in SQL Server's native BCP format:

- NOT NULL fixed-size types (int, datetime ...) are stored as raw little-endian bytes.
- Nullable fixed-size types have a 1-byte length prefix; 0xFF means NULL.
- bit always has the 1-byte prefix, even when the column is NOT NULL.
- (n)varchar(n) and varbinary(n) have a 2-byte length prefix; 0xFFFF means NULL.
- (n)varchar(max) and varbinary(max) have an 8-byte length prefix; all 0xFF means NULL.

Only the column types used by the old iglc.net database are supported; anything else raises.
Standard library only, so it can also be run on its own:  python -m apps.archive.bacpac export.bacpac
"""

from __future__ import annotations

import struct
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta

FIXED_SIZES = {"int": 4, "bigint": 8, "smallint": 2, "tinyint": 1, "bit": 1, "datetime": 8, "float": 8}
TEXT_ENCODINGS = {"nvarchar": "utf-16-le", "nchar": "utf-16-le", "varchar": "cp1252", "char": "cp1252"}
SQL_EPOCH = datetime(1900, 1, 1)


@dataclass
class Column:
    name: str
    type: str
    nullable: bool
    is_max: bool


class BacpacError(Exception):
    pass


class Bacpac:
    def __init__(self, path):
        self.zip = zipfile.ZipFile(path)
        self.tables = self._read_model()

    def _read_model(self) -> dict[str, list[Column]]:
        root = ET.fromstring(self.zip.read("model.xml"))
        ns = root.tag.split("}")[0] + "}"
        tables = {}
        for element in root.iter(f"{ns}Element"):
            if element.get("Type") != "SqlTable":
                continue
            table = element.get("Name").replace("[", "").replace("]", "")  # dbo.Papers
            columns = []
            for col in element.iter(f"{ns}Element"):
                if col.get("Type") != "SqlSimpleColumn":
                    continue
                props = {p.get("Name"): p.get("Value") for p in col.findall(f"{ns}Property")}
                sql_type, is_max = None, False
                for spec in col.iter(f"{ns}Element"):
                    if spec.get("Type") == "SqlTypeSpecifier":
                        spec_props = {p.get("Name"): p.get("Value") for p in spec.findall(f"{ns}Property")}
                        is_max = spec_props.get("IsMax") == "True"
                        for ref in spec.iter(f"{ns}References"):
                            sql_type = ref.get("Name").strip("[]")
                columns.append(Column(
                    name=col.get("Name").split(".")[-1].strip("[]"),
                    type=sql_type,
                    nullable=props.get("IsNullable") != "False",
                    is_max=is_max,
                ))
            tables[table] = columns
        return tables

    def rows(self, table: str):
        """Yield each row of a table (for example 'dbo.Papers') as a dict."""
        if table not in self.tables:
            raise BacpacError(f"No table {table} in the export")
        columns = self.tables[table]
        prefix = f"Data/{table}/"
        for name in sorted(n for n in self.zip.namelist() if n.startswith(prefix)):
            data = self.zip.read(name)
            pos = 0
            while pos < len(data):
                row = {}
                for column in columns:
                    row[column.name], pos = _read_value(data, pos, column)
                yield row
            if pos != len(data):
                raise BacpacError(f"{name}: {len(data) - pos} bytes left over")

    def count(self, table: str) -> int:
        return sum(1 for _ in self.rows(table))


def _read_value(data: bytes, pos: int, column: Column):
    t = column.type
    if t in FIXED_SIZES:
        size = FIXED_SIZES[t]
        if column.nullable or t == "bit":
            length = data[pos]
            pos += 1
            if length == 0xFF:
                return None, pos
            if length != size:
                raise BacpacError(f"{column.name}: unexpected length {length} for {t}")
        raw = data[pos:pos + size]
        return _decode_fixed(t, raw), pos + size

    if t in TEXT_ENCODINGS or t == "varbinary":
        if column.is_max:
            (length,) = struct.unpack_from("<q", data, pos)
            pos += 8
            if length == -1:
                return None, pos
        else:
            (length,) = struct.unpack_from("<H", data, pos)
            pos += 2
            if length == 0xFFFF:
                return None, pos
        raw = data[pos:pos + length]
        pos += length
        if t == "varbinary":
            return bytes(raw), pos
        return raw.decode(TEXT_ENCODINGS[t]), pos

    raise BacpacError(f"Column {column.name}: type {t} is not supported")


def _decode_fixed(t: str, raw: bytes):
    if t == "int":
        return struct.unpack("<i", raw)[0]
    if t == "bigint":
        return struct.unpack("<q", raw)[0]
    if t == "smallint":
        return struct.unpack("<h", raw)[0]
    if t == "tinyint":
        return raw[0]
    if t == "bit":
        return bool(raw[0])
    if t == "float":
        return struct.unpack("<d", raw)[0]
    if t == "datetime":
        days, ticks = struct.unpack("<iI", raw)
        return SQL_EPOCH + timedelta(days=days, milliseconds=round(ticks * 10 / 3))
    raise BacpacError(t)


if __name__ == "__main__":
    export = Bacpac(sys.argv[1])
    for table in sorted(export.tables):
        print(f"{table}: {export.count(table)} rows")
