@ECHO OFF
SET tooling_jar=tooling-cli-3.8.0.jar
SET input_cache_path=%~dp0input-cache
SET mat_bundle=input\tests\measure\CMS2FHIRPCSDepressionScreenAndFollowUp

SET JAVA_TOOL_OPTIONS=-Dfile.encoding=UTF-8

IF EXIST "%input_cache_path%\%tooling_jar%" (
	ECHO running: JAVA -jar "%input_cache_path%\%tooling_jar%" -BundleToResources -p=%mat_bundle% -v=r4 -op=%mat_bundle%
	JAVA -jar "%input_cache_path%\%tooling_jar%" -BundleToResources -p=%mat_bundle% -v=r4 -op=%mat_bundle%
) ELSE If exist "..\%tooling_jar%" (
	ECHO running: JAVA -jar "..\%tooling_jar%" -BundleToResources -p=%mat_bundle% -v=r4 -op=%mat_bundle%
	JAVA -jar "..\%tooling_jar%" -BundleToResources -p=%mat_bundle% -v=r4 -op=%mat_bundle%
) ELSE (
	ECHO Tooling JAR NOT FOUND in input-cache or parent folder.  Please run _updateCQFTooling.  Aborting...
)

PAUSE
