// 005 — Range indexes on `effective_from` for temporal queries (spec 015 FR-3).
// Lets retrieval prefilter by "as-of" date in O(log n).

CREATE INDEX statute_effective_from_idx IF NOT EXISTS
  FOR (s:Statute) ON (s.effective_from);

CREATE INDEX statute_section_effective_from_idx IF NOT EXISTS
  FOR (s:StatuteSection) ON (s.effective_from);

CREATE INDEX ordinance_effective_from_idx IF NOT EXISTS
  FOR (o:Ordinance) ON (o.effective_from);

CREATE INDEX ordinance_section_effective_from_idx IF NOT EXISTS
  FOR (o:OrdinanceSection) ON (o.effective_from);

CREATE INDEX regulation_effective_from_idx IF NOT EXISTS
  FOR (r:Regulation) ON (r.effective_from);
