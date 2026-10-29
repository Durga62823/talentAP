"""SQL validation, column lineage and query rewriting.

Every query is parsed with sqlglot (not regex). The whole syntax tree must consist of an
allow-listed set of node types; anything else (sub-queries, CTEs, UNION, functions,
CASE, casts, arithmetic, string concatenation, DDL/DML, PRAGMA ...) is rejected.

Lineage: each projection is resolved to exactly one source column (or an allow-listed
aggregate over one column). The query is then REWRITTEN with positional output aliases
(_c0, _c1 ...) so masking is applied by lineage, never by guessing from display names.

Inference protection: columns used in WHERE / GROUP BY / HAVING / ORDER BY must be ones the
caller can see raw. Otherwise a predicate such as `CARD_NO LIKE '4111%'` would leak a
masked value one guess at a time. JOIN ... ON equality between two columns is permitted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

from .policy import Decision

ALLOWED_NODES: tuple[type[exp.Expression], ...] = (
    exp.Select, exp.From, exp.Join, exp.Table, exp.TableAlias, exp.Identifier, exp.Column, exp.Star,
    exp.Alias, exp.Where, exp.Group, exp.Having, exp.Order, exp.Ordered, exp.Limit, exp.Offset,
    exp.Literal, exp.Boolean, exp.Null, exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.And, exp.Or, exp.Not, exp.Paren, exp.In, exp.Like, exp.ILike, exp.Between, exp.Is,
    exp.Neg, exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Distinct,
)
AGGREGATES = (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)
SYSTEM_TABLE_PREFIXES = ("sqlite_", "pg_")
SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast", "temp", "mysql", "performance_schema", "sys"}


class QueryRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Source:
    key: str  # alias (or table name when un-aliased), lowercase
    schema: str
    table: str  # actual name from metadata
    columns: list[str]  # actual column names, in table order


@dataclass
class OutputColumn:
    name: str
    kind: str  # column | aggregate
    schema: str | None
    table: str | None
    column: str | None
    aggregate: str | None
    decision: Decision | None
    action: str  # effective action applied to the output values

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "source": f"{self.table}.{self.column}" if self.column else None,
            "aggregate": self.aggregate,
            "action": self.action,
            "category": self.decision.category if self.decision else None,
            "sensitivity": self.decision.sensitivity if self.decision else None,
            "policy_id": self.decision.policy_id if self.decision else None,
            "policy_name": self.decision.policy_name if self.decision else None,
            "reason": self.decision.reason if self.decision else "aggregate over permitted input",
        }


@dataclass
class QueryPlan:
    sql: str
    outputs: list[OutputColumn]
    tables: list[str]
    referenced_columns: list[str]
    predicate_columns: list[str]
    min_group_enforced: int | None = None
    notes: list[str] = field(default_factory=list)


# Callback types supplied by the query engine
TableLookup = Callable[[str | None, str], tuple[str, str, list[str]] | None]  # (schema?, name) -> (schema, table, cols)
DecisionLookup = Callable[[str, str, str], Decision]


def parse_single_select(sql: str, dialect: str) -> exp.Select:
    if not sql or not sql.strip():
        raise QueryRejected("empty", "Query is empty")
    if len(sql) > 10_000:
        raise QueryRejected("too_long", "Query exceeds 10,000 characters")
    try:
        trees = [t for t in sqlglot.parse(sql, read=dialect) if t is not None]
    except (ParseError, TokenError):
        raise QueryRejected("parse_error", "Query could not be parsed as supported SQL") from None
    if len(trees) != 1:
        raise QueryRejected("multiple_statements", "Exactly one statement is allowed")
    tree = trees[0]
    if not isinstance(tree, exp.Select):
        kind = type(tree).__name__.upper()
        raise QueryRejected("not_select", f"Only read-only SELECT statements are permitted (got {kind})")
    for node in tree.walk():
        if not isinstance(node, ALLOWED_NODES):
            name = type(node).__name__
            if isinstance(node, (exp.Subquery, exp.Union, exp.With, exp.CTE)) or (isinstance(node, exp.Select) and node is not tree):
                raise QueryRejected("nested_query", "Sub-queries, CTEs and set operations are not supported: lineage cannot be guaranteed")
            if isinstance(node, exp.Func):
                raise QueryRejected("unsupported_function", f"Function '{name}' is not permitted; only COUNT/SUM/AVG/MIN/MAX over a single column")
            raise QueryRejected("unsupported_expression", f"Expression type '{name}' is not permitted")
        if isinstance(node, exp.Select) and node is not tree:
            raise QueryRejected("nested_query", "Sub-queries are not supported: lineage cannot be guaranteed")
    for key in ("with", "into", "locks", "windows", "qualify", "connect", "sample", "laterals", "pivots", "settings", "format", "options"):
        if tree.args.get(key):
            raise QueryRejected("unsupported_clause", f"Clause '{key.upper()}' is not permitted")
    if not tree.args.get("from"):
        raise QueryRejected("no_table", "Query must select from a table")
    return tree


def plan_query(
    sql: str,
    dialect: str,
    lookup_table: TableLookup,
    decide: DecisionLookup,
    *,
    max_rows: int,
    min_group: int,
    qualify_schema: bool,
) -> QueryPlan:
    tree = parse_single_select(sql, dialect)

    # ---- sources -----------------------------------------------------------------------
    table_nodes: list[exp.Table] = [tree.args["from"].this]
    for j in tree.args.get("joins") or []:
        if j.args.get("using"):
            raise QueryRejected("join_using", "JOIN ... USING is not supported; use explicit ON conditions")
        if (j.args.get("method") or "").upper() == "NATURAL" or (j.text("kind") or "").upper() == "NATURAL":
            raise QueryRejected("natural_join", "NATURAL JOIN is not supported")
        table_nodes.append(j.this)

    sources: dict[str, Source] = {}
    for t in table_nodes:
        if not isinstance(t, exp.Table) or not isinstance(t.this, exp.Identifier):
            raise QueryRejected("unsupported_source", "Only plain table references are supported")
        if t.args.get("catalog"):
            raise QueryRejected("unauthorized_table", "Cross-database references are not permitted")
        schema = t.text("db") or None
        name = t.name
        if name.lower().startswith(SYSTEM_TABLE_PREFIXES) or (schema and schema.lower() in SYSTEM_SCHEMAS):
            raise QueryRejected("system_catalog", "System catalog access is not permitted")
        resolved = lookup_table(schema, name)
        if resolved is None:
            raise QueryRejected("unauthorized_table", f"Table '{name}' does not exist or is not authorized for your role")
        r_schema, r_table, r_cols = resolved
        key = (t.alias or name).lower()
        if key in sources:
            raise QueryRejected("duplicate_alias", f"Table alias '{key}' is used more than once")
        sources[key] = Source(key, r_schema, r_table, r_cols)
        # Normalise the table reference to the real identifiers.
        t.set("this", exp.to_identifier(r_table, quoted=True))
        t.set("db", exp.to_identifier(r_schema, quoted=True) if qualify_schema else None)
        if t.alias:
            t.set("alias", exp.TableAlias(this=exp.to_identifier(key, quoted=True)))

    decisions: dict[tuple[str, str, str], Decision] = {}

    def decision_for(src: Source, col: str) -> Decision:
        k = (src.schema, src.table, col)
        if k not in decisions:
            decisions[k] = decide(src.schema, src.table, col)
        return decisions[k]

    def resolve(col: exp.Column) -> tuple[Source, str]:
        cname = col.name
        qualifier = col.table
        if qualifier:
            if col.text("db") or col.text("catalog"):
                raise QueryRejected("unsupported_reference", "Use table aliases instead of schema-qualified columns")
            src = sources.get(qualifier.lower())
            if src is None:
                raise QueryRejected("unknown_table_ref", f"Unknown table reference '{qualifier}'")
            matches = [c for c in src.columns if c.lower() == cname.lower()]
            if not matches:
                raise QueryRejected("unknown_column", f"Column '{qualifier}.{cname}' does not exist")
            return src, matches[0]
        found = [(s, c) for s in sources.values() for c in s.columns if c.lower() == cname.lower()]
        if not found:
            raise QueryRejected("unknown_column", f"Column '{cname}' does not exist in the referenced tables")
        if len(found) > 1:
            raise QueryRejected("ambiguous_column", f"Column '{cname}' is ambiguous; qualify it with a table alias")
        return found[0]

    def rewrite_column(col: exp.Column, src: Source, actual: str) -> None:
        col.set("this", exp.to_identifier(actual, quoted=True))
        col.set("table", exp.to_identifier(src.key, quoted=True))

    referenced: set[str] = set()

    def deny_check(src: Source, actual: str) -> Decision:
        d = decision_for(src, actual)
        referenced.add(f"{src.table}.{actual}")
        if d.action == "DENY":
            raise QueryRejected("column_denied", f"Access to column '{src.table}.{actual}' is denied by policy ({d.reason})")
        return d

    # ---- projections ---------------------------------------------------------------------
    outputs: list[OutputColumn] = []
    new_projection: list[exp.Expression] = []
    alias_to_index: dict[str, int] = {}
    uses_aggregate_only = False
    has_aggregate = False

    def add_output(expr: exp.Expression, out: OutputColumn) -> None:
        idx = len(outputs)
        outputs.append(out)
        new_projection.append(exp.alias_(expr, f"_c{idx}", quoted=True))

    for proj in tree.expressions:
        alias = proj.alias if isinstance(proj, exp.Alias) else None
        inner = proj.this if isinstance(proj, exp.Alias) else proj

        if isinstance(inner, exp.Star) or (isinstance(inner, exp.Column) and isinstance(inner.this, exp.Star)):
            if alias:
                raise QueryRejected("unsupported_expression", "A wildcard cannot be aliased")
            if isinstance(inner, exp.Column):
                src = sources.get(inner.table.lower())
                if src is None:
                    raise QueryRejected("unknown_table_ref", f"Unknown table reference '{inner.table}'")
                targets = [src]
            else:
                targets = list(sources.values())
            for src in targets:
                for actual in src.columns:
                    d = deny_check(src, actual)
                    col = exp.column(actual, table=src.key, quoted=True)
                    add_output(col, OutputColumn(actual, "column", src.schema, src.table, actual, None, d, d.action))
            continue

        if isinstance(inner, exp.Column):
            src, actual = resolve(inner)
            d = deny_check(src, actual)
            rewrite_column(inner, src, actual)
            name = alias or actual
            if alias:
                alias_to_index[alias.lower()] = len(outputs)
            add_output(inner, OutputColumn(name, "column", src.schema, src.table, actual, None, d, d.action))
            continue

        if isinstance(inner, AGGREGATES):
            has_aggregate = True
            fn = type(inner).__name__.upper()
            arg = inner.this
            distinct = isinstance(arg, exp.Distinct)
            if distinct:
                if len(arg.expressions) != 1:
                    raise QueryRejected("unsupported_expression", "DISTINCT aggregates over one column only")
                arg = arg.expressions[0]
            label = alias or inner.sql(dialect=dialect)
            if isinstance(arg, exp.Star):
                if fn != "COUNT":
                    raise QueryRejected("unsupported_expression", f"{fn}(*) is not valid")
                if alias:
                    alias_to_index[alias.lower()] = len(outputs)
                add_output(inner, OutputColumn(label, "aggregate", None, None, None, fn, None, "ALLOW"))
                continue
            if not isinstance(arg, exp.Column) or isinstance(arg.this, exp.Star):
                raise QueryRejected("computed_expression", "Aggregates must be applied to a single column")
            src, actual = resolve(arg)
            d = deny_check(src, actual)
            rewrite_column(arg, src, actual)
            if fn == "COUNT":
                action = "ALLOW"  # counting reveals no values
            elif d.action == "ALLOW":
                action = "ALLOW"
            elif d.action == "AGGREGATE_ONLY" and fn in ("SUM", "AVG"):
                action = "ALLOW"
                uses_aggregate_only = True
            else:
                raise QueryRejected(
                    "aggregate_denied",
                    f"{fn} over '{src.table}.{actual}' is not permitted (policy action {d.action})",
                )
            if alias:
                alias_to_index[alias.lower()] = len(outputs)
            add_output(inner, OutputColumn(label, "aggregate", src.schema, src.table, actual, fn, d, action))
            continue

        raise QueryRejected(
            "computed_expression",
            "Computed expressions and literals in the select list are not supported: lineage cannot be established",
        )

    if not outputs:
        raise QueryRejected("no_columns", "Query returns no columns")

    # ---- predicates / grouping / ordering ------------------------------------------------
    predicate_cols: set[str] = set()

    def check_predicate_columns(node: exp.Expression | None, clause: str, allow_alias: bool) -> None:
        if node is None:
            return
        for col in list(node.find_all(exp.Column)):
            if isinstance(col.this, exp.Star):
                raise QueryRejected("unsupported_expression", f"Wildcard not allowed in {clause}")
            if allow_alias and not col.table and col.name.lower() in alias_to_index:
                idx = alias_to_index[col.name.lower()]
                out = outputs[idx]
                if out.kind == "column" and out.action != "ALLOW":
                    raise QueryRejected("predicate_on_protected", f"{clause} on protected column '{out.name}' is not permitted")
                col.replace(exp.column(f"_c{idx}", quoted=True))
                continue
            src, actual = resolve(col)
            d = deny_check(src, actual)
            predicate_cols.add(f"{src.table}.{actual}")
            in_aggregate = col.find_ancestor(*AGGREGATES) is not None
            if d.action != "ALLOW" and not (in_aggregate and clause == "HAVING" and d.action == "AGGREGATE_ONLY"):
                raise QueryRejected(
                    "predicate_on_protected",
                    f"{clause} references protected column '{src.table}.{actual}' ({d.action}); filtering or sorting on "
                    "masked data could reveal it by inference",
                )
            rewrite_column(col, src, actual)

    check_predicate_columns(tree.args.get("where"), "WHERE", allow_alias=False)
    check_predicate_columns(tree.args.get("group"), "GROUP BY", allow_alias=True)
    check_predicate_columns(tree.args.get("having"), "HAVING", allow_alias=True)
    check_predicate_columns(tree.args.get("order"), "ORDER BY", allow_alias=True)

    for j in tree.args.get("joins") or []:
        on = j.args.get("on")
        if on is None:
            continue
        for col in list(on.find_all(exp.Column)):
            src, actual = resolve(col)
            d = deny_check(src, actual)
            parent = col.parent
            pure_equi = isinstance(parent, exp.EQ) and isinstance(parent.this, exp.Column) and isinstance(parent.expression, exp.Column)
            if d.action != "ALLOW" and not pure_equi:
                raise QueryRejected(
                    "predicate_on_protected",
                    f"JOIN condition on protected column '{src.table}.{actual}' must be a column-to-column equality",
                )
            predicate_cols.add(f"{src.table}.{actual}")
            rewrite_column(col, src, actual)

    # ---- rewrite projection, k-threshold, limit ------------------------------------------
    tree.set("expressions", new_projection)
    min_group_enforced = None
    notes: list[str] = []
    if uses_aggregate_only:
        threshold = exp.GTE(this=exp.Count(this=exp.Star()), expression=exp.Literal.number(min_group))
        existing = tree.args.get("having")
        cond = exp.and_(existing.this, threshold) if existing else threshold
        tree.set("having", exp.Having(this=cond))
        min_group_enforced = min_group
        notes.append(f"Groups with fewer than {min_group} rows are suppressed (aggregate-only policy)")
    elif has_aggregate and not tree.args.get("group"):
        pass

    limit_node = tree.args.get("limit")
    user_limit = None
    if limit_node is not None:
        lit = limit_node.expression if isinstance(limit_node, exp.Limit) else None
        if not isinstance(lit, exp.Literal) or not lit.is_int:
            raise QueryRejected("invalid_limit", "LIMIT must be an integer literal")
        user_limit = int(lit.this)
    offset = tree.args.get("offset")
    if offset is not None and not (isinstance(offset.expression, exp.Literal) and offset.expression.is_int):
        raise QueryRejected("invalid_limit", "OFFSET must be an integer literal")
    effective = max_rows + 1 if user_limit is None else min(user_limit, max_rows + 1)
    tree.set("limit", exp.Limit(expression=exp.Literal.number(effective)))

    return QueryPlan(
        sql=tree.sql(dialect=dialect),
        outputs=outputs,
        tables=sorted({s.table for s in sources.values()}),
        referenced_columns=sorted(referenced),
        predicate_columns=sorted(predicate_cols),
        min_group_enforced=min_group_enforced,
        notes=notes,
    )
