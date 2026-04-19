#!/bin/bash
#DO NOT EDIT WITH WINDOWS
tooling_jar=tooling-cli-3.8.0.jar
input_cache_path=./input-cache
mat_bundle=input/tests/measure/CMS1056CTClinicalFHIR


set -e

tooling=$input_cache_path/$tooling_jar


if test -f "$tooling"; then
	echo running: JAVA -jar $tooling -BundleToResources -p=$mat_bundle -v=r4 -op=$mat_bundle
	java -jar $tooling -BundleToResources -p=$mat_bundle -v=r4 -op=$mat_bundle
else
	tooling=../$tooling_jar
	echo $tooling
	if test -f "$tooling"; then
		echo running: JAVA -jar $tooling -BundleToResources -p=$mat_bundle -v=r4 -op=$mat_bundle
		java -jar $tooling -BundleToResources -p=$mat_bundle -v=r4 -op=$mat_bundle
	else
		echo Tooling JAR NOT FOUND in input-cache or parent folder.  Please run _updateCQFTooling.  Aborting...
	fi
fi