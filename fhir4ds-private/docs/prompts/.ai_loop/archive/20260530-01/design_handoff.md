# Design Handoff: Mongo FHIR Server Source

The feature design is complete and ready for human approval.

Final plan:

`docs/architecture/plans/FEATURE_MONGO_FHIR_SERVER_SOURCE.md`

The plan designs a read-only `MongoFhirServerSource` that mounts Mongo-backed
FHIR server current resources through DuckDB's community `mongo` extension as
the standard FHIR4DS `resources` view. It starts with the verified Helix
collection convention `{ResourceType}_4_0_0`, keeps history/audit/access-log
collections out of scope, excludes Helix hidden resources by default, and makes
schema inference a mandatory correctness gate before implementation proceeds.

Refinement after user feedback: Mongo layout configurability is now a first
class design point. The final plan includes explicit per-resource collection
layout mappings through `MongoResourceCollection`, including custom collection
names, wrapped FHIR resource paths, custom id/resourceType JSON paths, and
configured current/deleted filters. The API continues to own SQL generation
rather than accepting arbitrary SQL.

The architecture self-audit found five draft risks and the final plan addresses
them:

- collection/current-resource proof is now explicit
- DuckDB Mongo schema inference must be verified with `sample_size := -1`
- hidden-resource policy is configurable and tested
- credential redaction has an assigned helper and acceptance criteria
- Docker scope is split into a minimum Mongo-only smoke and optional full Helix
  profiles

The next workflow must not proceed to implementation until the user approves the
final plan by saying `APPROVED` or `EXECUTE`, or by updating
`USER_DIRECTIVES.md` accordingly.
