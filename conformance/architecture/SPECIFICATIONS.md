# Healthcare Interoperability Specifications Reference

**Document Version**: 1.0
**Date**: 2025-01-21
**Status**: Reference Documentation

---

## Overview

This document provides comprehensive links to all healthcare interoperability specifications that FHIR4DS targets for 100% compliance, along with official testing resources and community documentation.

---

## Core Specifications

### FHIRPath R4 Specification

**FHIR4DS Target**: 100% compliance (currently 0.9%)

#### Official Specification
- **Primary Specification**: [FHIRPath R4 Specification](https://hl7.org/fhirpath/)
- **Grammar Definition**: [FHIRPath Grammar](https://hl7.org/fhirpath/grammar.html)
- **Function Library**: [FHIRPath Functions](https://hl7.org/fhirpath/functions.html)
- **Implementation Guide**: [FHIRPath Implementation Guide](https://hl7.org/fhir/R4/fhirpath.html)

#### Official Testing Resources
- **Test Cases Repository**: [FHIRPath Test Cases](https://github.com/HL7/FHIRPath/tree/master/tests)
- **Reference Implementation**: [FHIRPath JavaScript](https://github.com/HL7/fhirpath.js)
- **Test Runner**: [FHIRPath Test Runner](https://github.com/HL7/FHIRPath/tree/master/tests)
- **Validation Suite**: [FHIRPath Validation](https://github.com/HL7/fhir-test-cases/tree/master/r4/fhirpath)

#### Community Resources
- **HL7 FHIR Chat**: [FHIRPath Stream on Zulip](https://chat.fhir.org/#narrow/stream/179266-fhirpath)
- **FHIR Specification**: [FHIR R4 FHIRPath Page](https://hl7.org/fhir/R4/fhirpath.html)
- **Implementation Examples**: [FHIR FHIRPath Examples](https://hl7.org/fhir/R4/fhirpath.html#examples)

#### Key Implementation Areas
- **Path Navigation**: Resource traversal and property access
- **Collection Operations**: where(), select(), all(), any(), exists()
- **String Functions**: contains(), startsWith(), matches(), replace()
- **Math Functions**: abs(), ceiling(), floor(), round(), sqrt()
- **Date/Time Functions**: today(), now(), temporal arithmetic
- **Type Operations**: as(), is(), ofType(), convertsToString()

### SQL-on-FHIR Specification

**FHIR4DS Target**: Maintain 100% compliance (currently achieved)

#### Official Specification
- **Primary Specification**: [SQL-on-FHIR v2.0](https://sql-on-fhir-v2.readthedocs.io/en/latest/)
- **Implementation Guide**: [SQL-on-FHIR Implementation Guide](https://sql-on-fhir-v2.readthedocs.io/en/latest/implementation.html)
- **ViewDefinition Schema**: [ViewDefinition Structure](https://sql-on-fhir-v2.readthedocs.io/en/latest/viewdefinition.html)
- **Column Specification**: [Column Definition Format](https://sql-on-fhir-v2.readthedocs.io/en/latest/columns.html)

#### Official Testing Resources
- **Test Cases Repository**: [SQL-on-FHIR Test Cases](https://github.com/sql-on-fhir-v2/sql-on-fhir-v2/tree/main/tests)
- **Reference Implementation**: [SQL-on-FHIR Reference](https://github.com/sql-on-fhir-v2/sql-on-fhir-v2)
- **Validation Suite**: [SQL-on-FHIR Validation](https://github.com/sql-on-fhir-v2/sql-on-fhir-v2/tree/main/validator)
- **Sample Data**: [SQL-on-FHIR Test Data](https://github.com/sql-on-fhir-v2/sql-on-fhir-v2/tree/main/testdata)

#### Community Resources
- **Project Website**: [SQL-on-FHIR Official Site](https://sql-on-fhir.org/)
- **Community Discussions**: [SQL-on-FHIR Discussions](https://github.com/sql-on-fhir-v2/sql-on-fhir-v2/discussions)
- **FHIR ImplementationGuide**: [SQL-on-FHIR IG](http://hl7.org/fhir/uv/sql-on-fhir/2022Jan/)

#### Key Implementation Areas
- **ViewDefinition Processing**: Converting FHIR views to SQL queries
- **Column Generation**: Proper column naming and data type handling
- **FHIRPath Integration**: FHIRPath expressions in column definitions
- **Nested Data**: JSON path extraction and complex data flattening
- **Performance**: Population-scale query optimization

### CQL Framework Specification

**FHIR4DS Target**: 100% compliance (currently 59.2%)

#### Official Specification
- **CQL Specification**: [Clinical Quality Language (CQL) R1.5](https://cql.hl7.org/09-b-cqlreference.html)
- **Language Guide**: [CQL Language Guide](https://cql.hl7.org/)
- **Grammar Definition**: [CQL Grammar](https://cql.hl7.org/19-l-cqlsyntaxdiagrams.html)
- **Data Model**: [CQL FHIR Data Model](https://cql.hl7.org/07-physicalrepresentation.html#data-model)

#### Official Testing Resources
- **CQL Test Cases**: [CQL Test Suite](https://github.com/cqframework/cql-tests)
- **Reference Engine**: [CQL Engine](https://github.com/cqframework/cql-engine)
- **Execution Framework**: [CQL Execution Framework](https://github.com/cqframework/cql-execution)
- **Translation Tools**: [CQL Translation Service](https://github.com/cqframework/cql-translation-service)

#### Community Resources
- **CQL Community**: [HL7 CQL Community](https://confluence.hl7.org/display/CQLWG)
- **Implementation Guide**: [Using CQL with FHIR](http://hl7.org/fhir/uv/cql/)
- **CQFramework**: [Clinical Quality Framework](https://github.com/cqframework)
- **FHIR Chat**: [CQL Stream on Zulip](https://chat.fhir.org/#narrow/stream/179220-cql)

#### Key Implementation Areas
- **Library Management**: CQL library loading, versioning, dependencies
- **Expression Evaluation**: All CQL operators and expression types
- **Data Access**: FHIR resource access and path navigation
- **Function Library**: Built-in CQL functions and operators
- **Terminology**: Value set and code system integration
- **Date/Time**: Temporal operations and precision handling

### Quality Measure Specifications

**FHIR4DS Target**: 100% compliance with eCQI Framework

#### Official Specifications
- **eCQI Framework**: [Electronic Clinical Quality Improvement](https://ecqi.healthit.gov/)
- **FHIR Measures**: [FHIR R4 Measure Resource](https://hl7.org/fhir/R4/measure.html)
- **Quality Reporting**: [FHIR R4 MeasureReport](https://hl7.org/fhir/R4/measurereport.html)
- **CMS eCQMs**: [CMS Electronic Clinical Quality Measures](https://ecqi.healthit.gov/ecqms)

#### Official Testing Resources
- **CMS Test Cases**: [eCQM Test Cases](https://github.com/cqframework/cqm-tests)
- **MAT (Measure Authoring Tool)**: [CMS MAT](https://www.emeasuretool.cms.gov/)
- **Cypress Test Suite**: [Quality Measure Testing](https://github.com/projectcypress/cypress)
- **FHIR Measure Examples**: [FHIR Measure Examples](https://github.com/cqframework/sample-content-ig)

#### CMS eCQM Specifications
- **CMS Quality Measures**: [2024 CMS eCQMs](https://ecqi.healthit.gov/eligible-professional-eligible-clinician-ecqms)
- **Hospital Quality Measures**: [2024 Hospital eCQMs](https://ecqi.healthit.gov/eligible-hospital-critical-access-hospital-ecqms)
- **Implementation Guides**: [eCQM Implementation Guides](https://ecqi.healthit.gov/ecqm-implementation-guides)

#### Key Implementation Areas
- **Measure Calculation**: Population criteria evaluation
- **Stratification**: Population stratification and supplemental data
- **Data Requirements**: Automatic data requirement generation
- **Report Generation**: FHIR MeasureReport resource creation
- **Performance**: Population-scale measure calculation

---

## Testing and Validation Resources

### Official Test Repositories

#### FHIRPath Testing
```
Repository: https://github.com/HL7/FHIRPath/tree/master/tests
Structure:
├── tests/
│   ├── r4/
│   │   ├── fhirpath/
│   │   │   ├── fhirpath-r4.json
│   │   │   └── test-cases/
│   │   └── resources/
│   └── utilities/
```

#### SQL-on-FHIR Testing
```
Repository: https://github.com/sql-on-fhir-v2/sql-on-fhir-v2/tree/main/tests
Structure:
├── tests/
│   ├── viewdefinition/
│   ├── column/
│   ├── integration/
│   └── performance/
├── testdata/
│   ├── r4/
│   └── synthetic/
```

#### CQL Testing
```
Repository: https://github.com/cqframework/cql-tests
Structure:
├── tests/
│   ├── CqlTestSuite/
│   ├── ELMTestSuite/
│   └── TranslationTestSuite/
├── resources/
│   ├── fhir/
│   └── terminology/
```

### FHIR4DS Test Integration

#### Current Test Structure
```
fhir4ds/tests/
├── official/
│   ├── sql-on-fhir/          # SQL-on-FHIR test cases
│   └── fhirpath/             # FHIRPath R4 test cases
├── unit/                     # Unit tests
├── integration/              # Integration tests
└── performance/              # Performance benchmarks
```

#### Test Execution Commands
```bash
# Run all SQL-on-FHIR tests
python tests/run_tests.py --dialect all

# Run FHIRPath R4 tests
python tests/official/fhirpath/fhirpath_r4_test_runner.py

# Run comprehensive compliance tests
python tests/run_comprehensive_compliance.py

# Run CQL tests (when implemented)
python tests/run_cql_tests.py
```

---

## Reference Implementation Links

### FHIRPath Reference Implementations

#### JavaScript (Official HL7)
- **Repository**: [fhirpath.js](https://github.com/HL7/fhirpath.js)
- **Usage**: Primary reference for behavior validation
- **NPM Package**: [@types/fhirpath](https://www.npmjs.com/package/fhirpath)

#### Java (HAPI FHIR)
- **Repository**: [HAPI FHIR FHIRPath](https://github.com/hapifhir/hapi-fhir/tree/master/hapi-fhir-base/src/main/java/ca/uhn/fhir/util)
- **Documentation**: [HAPI FHIR FHIRPath](https://hapifhir.io/hapi-fhir/docs/model/parsers.html#fhirpath-tester)

#### .NET (Firely SDK)
- **Repository**: [Firely .NET SDK](https://github.com/FirelyTeam/firely-net-sdk)
- **NuGet Package**: [Hl7.FhirPath](https://www.nuget.org/packages/Hl7.FhirPath/)

### SQL-on-FHIR Reference Implementations

#### Google SQL-on-FHIR
- **Repository**: [SQL-on-FHIR v2 Reference](https://github.com/sql-on-fhir-v2/sql-on-fhir-v2)
- **Documentation**: [Implementation Guide](https://sql-on-fhir-v2.readthedocs.io/)

### CQL Reference Implementations

#### Java CQL Engine
- **Repository**: [CQL Engine](https://github.com/cqframework/cql-engine)
- **Maven Artifact**: [org.opencds.cqf:cql-engine](https://search.maven.org/artifact/org.opencds.cqf/cql-engine)

#### JavaScript CQL Execution
- **Repository**: [CQL Execution](https://github.com/cqframework/cql-execution)
- **NPM Package**: [cql-execution](https://www.npmjs.com/package/cql-execution)

---

## Standards Organizations and Communities

### HL7 International

#### Primary Organization
- **Website**: [HL7.org](https://www.hl7.org/)
- **FHIR Specification**: [FHIR R4](https://hl7.org/fhir/R4/)
- **Work Groups**: [FHIR Infrastructure](https://www.hl7.org/special/committees/fhir-i/)

#### Community Engagement
- **FHIR Chat**: [chat.fhir.org](https://chat.fhir.org/)
- **Confluence**: [FHIR Confluence](https://confluence.hl7.org/display/FHIR)
- **GitHub**: [HL7 FHIR GitHub](https://github.com/HL7/fhir)

### Clinical Quality Framework

#### CQFramework Community
- **Website**: [CQFramework.info](https://cqframework.info/)
- **GitHub**: [CQFramework Organization](https://github.com/cqframework)
- **Documentation**: [CQF Implementation Guide](https://build.fhir.org/ig/HL7/cqf-recommendations/)

### SQL-on-FHIR Community

#### Google Health Team
- **Project Site**: [SQL-on-FHIR.org](https://sql-on-fhir.org/)
- **GitHub**: [SQL-on-FHIR v2](https://github.com/sql-on-fhir-v2)
- **Discussions**: [Community Discussions](https://github.com/sql-on-fhir-v2/sql-on-fhir-v2/discussions)

---

## Development and Testing Tools

### Online Testing Tools

#### FHIRPath Tester
- **HAPI FHIR Tester**: [FHIRPath Tester](https://fhirserver.hl7.org.au/fhirpath/index.html)
- **Simplifier.net**: [FHIRPath Testing](https://simplifier.net/packages/hl7.fhir.r4.core/4.0.1/files/831885)

#### CQL Testing
- **CQL Runner**: [CDS Hooks CQL Runner](https://cql-runner.dataphoria.org/)
- **MAT Testing**: [CMS Measure Authoring Tool](https://www.emeasuretool.cms.gov/)

### Development Libraries

#### Python FHIR Libraries
- **fhir.resources**: [PyPI fhir.resources](https://pypi.org/project/fhir.resources/)
- **fhirclient**: [PyPI fhirclient](https://pypi.org/project/fhirclient/)

#### SQL Database Tools
- **DuckDB**: [DuckDB.org](https://duckdb.org/)
- **PostgreSQL**: [PostgreSQL.org](https://www.postgresql.org/)

---

## Compliance Monitoring and Reporting

### Automated Testing Integration

#### Continuous Integration
- **GitHub Actions**: Automated test execution on every commit
- **Test Reporting**: Detailed compliance reports generated automatically
- **Performance Monitoring**: Continuous performance benchmarking
- **Regression Detection**: Immediate alerts for compliance degradation

#### Quality Gates
- **Pre-commit Hooks**: Prevent non-compliant code from entering repository
- **Pull Request Validation**: Comprehensive testing before merge
- **Release Validation**: Complete compliance verification before release
- **Production Monitoring**: Ongoing compliance monitoring in production

### Compliance Dashboard

#### Real-time Metrics
- **FHIRPath Compliance**: Current pass rate and trending
- **SQL-on-FHIR Compliance**: Maintenance of 100% compliance
- **CQL Compliance**: Progress toward 100% compliance
- **Performance Metrics**: Query execution times and resource usage

#### Historical Tracking
- **Compliance Trends**: Long-term compliance improvement tracking
- **Performance Evolution**: Historical performance data and optimization progress
- **Issue Resolution**: Time-to-resolution for compliance issues
- **Release Quality**: Compliance metrics for each software release

---

## Conclusion

This comprehensive reference provides the foundation for FHIR4DS's commitment to 100% compliance with all major healthcare interoperability specifications. Regular review and updates of these references ensure that FHIR4DS remains aligned with the latest specification versions and community best practices.

The combination of official specifications, comprehensive testing resources, and active community engagement creates a robust foundation for building and maintaining a world-class healthcare interoperability platform.

---

*This reference guide is actively maintained and updated as specifications evolve and new resources become available.*