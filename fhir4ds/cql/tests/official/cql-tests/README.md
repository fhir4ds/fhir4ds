# CQL Tests Repository

This repository contains a suite of test cases for [Clinical Quality Language](http://cql.hl7.org) that allow implementations to determine the correct expected behavior of CQL language capabilities. The tests here were initially copied from the informative test cases published as part of the CQL specification. 

* [Github permalink to initial source](https://github.com/HL7/cql/tree/v1.5.2/tests)

## Test Case Format

The test cases are expressed in an XML format that is common across the FHIRPath and CQL specifications, documented in the XML Schema file:

* [Test Schema](tests/testSchema.xsd)

## Running the Tests

In addition to being part of the CI Build for several implementations, these tests can be run using the [CQL Tests Runner](https://github.com/cqframework/cql-tests-runner)

## Change Management

Changes to the tests maintained within this repository are managed using as lightweight a process as possible, while still ensuring stable, viable, production quality software. These processes are described in the [Change Management](CHANGE_MANAGEMENT.md) topic.

## Documentation

Documentation for this repository is maintained in the [wiki](https://github.com/cqframework/cql-tests/wiki)
