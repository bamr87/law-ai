// Migration 002 — initialize Case.aliases on legacy nodes (spec 002).
MATCH (c:Case) WHERE c.aliases IS NULL SET c.aliases = [];
