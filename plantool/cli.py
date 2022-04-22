from __future__ import annotations

from typing import Iterator, Mapping, TextIO

import click
import sqlparse
from sqlparse import sql, tokens as t

try:
    import lxml.etree as ET
except ImportError:
    import xml.etree.ElementTree as ET

NS = {
    "sp": "http://schemas.microsoft.com/sqlserver/2004/07/showplan",
}


def parse_plan(
    plan_file: TextIO,
) -> Iterator[tuple[sql.Statement | None, Mapping[str, str]]]:
    root = ET.parse(plan_file).getroot()
    for stmt_el in root.iterfind(
        "./sp:BatchSequence/sp:Batch/sp:Statements/sp:StmtSimple", NS
    ):
        stmt = None
        if text := stmt_el.attrib.get("StatementText"):
            stmt = sqlparse.parse(text)[0]

        yield stmt, {
            el.attrib["Column"]: el.attrib["ParameterCompiledValue"]
            for el in stmt_el.iterfind(
                "./sp:QueryPlan/sp:ParameterList/sp:ColumnReference", NS
            )
        }


def replace_params(root: sql.TokenList, params: Mapping[str, str]) -> sql.TokenList:
    tokens = []
    for token in root.tokens:
        if token.match(t.Name, values=params.keys()):
            tokens.append(sql.Token(t.Name, params[token.value]))
        elif isinstance(token, sql.TokenList):
            tokens.append(replace_params(token, params))
        else:
            tokens.append(token)
    return type(root)(tokens)

@click.group()
def cli() -> None:
    pass

@cli.command()
@click.argument("plan_file", type=click.File(encoding="utf-16"))
@click.argument("script", type=click.File(encoding="utf-8"), required=False)
def inline(plan_file: TextIO, script: TextIO | None) -> None:
    stmts = parse_plan(plan_file)

    if script is not None:
        stmts = zip(
            (stmt for stmt in sqlparse.parsestream(script) if not stmt.is_whitespace),
            (params for _, params in stmts),
        )

    for stmt, params in stmts:
        if not stmt:
            continue
        click.echo(
            sqlparse.format(
                str(replace_params(stmt, params)),
                keyword_case="upper",
                reindent=True,
                reindent_align=False,
                wrap_after=100,
            )
        )


@cli.command()
@click.argument("script", type=click.File(encoding="utf-8"))
def dump(script: TextIO) -> None:
    for stmt in sqlparse.parsestream(script):
        # pylint: disable=protected-access
        stmt._pprint_tree()


def main() -> None:
    # pylint: disable=no-value-for-parameter
    cli()


if __name__ == "__main__":
    main()
