"""Deterministic LSAT item synthesis (spec 049).

The engine derives items from formal skeletons and *proves* the credited
answer with a finite-model checker, so accuracy is a property of the
construction rather than something a reviewer has to certify. Surface
vocabulary comes from swappable domain packs that contain no logic, so one
proved skeleton yields as many distinct items as there are domains and seeds.

See :mod:`law_ai.lsat.synth.logic` for the checker and ``docs/lsat-synthesis.md``
for the authoring guide.
"""

ENGINE_VERSION = "synth/1"
