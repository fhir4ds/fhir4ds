# Engineer Handoff — SOF-VD-10 SKEPTIC (2026-08-23)

## Triage
- QA-001 (LOW): plain ValueError vs typed ValidationError at direct-dataclass
  __post_init__ boundary. Terminal INTENDED — no fix. Rationale: SQLOnFHIRError
  subclasses ValueError (SOF-VD-01 HISTORIAN backward-compat contract), so
  `except ValueError` behavior is identical; the strict official-JSON parse
  boundary wraps every validator raise into typed ParseError; the observation
  is a consistency nit, not a functional divergence or spec violation.
  Minimal Footprint forbids churning types.py raise sites for zero behavior
  change.
- QA-002 (LOW): profile canonical arrays accept `|`/`#`. Terminal INTENDED —
  spec-grounded: SD 2.0.0 defines NO constraint on ViewDefinition.profile;
  FHIR canonical form is `<url>[|<version>[|<fragment>]]` with regex \S*;
  whitespace rejection (the only normative lexical rule) is enforced.

## Code changes
None required. Zero OPEN/CONFIRMED issues; no fixes attempted; no
reproducers failing. Baselines verified post-triage on the unchanged FINAL
tree: viewdef pytest 1227/1227, conformance 2832/2832 (ViewDef 144/144).
