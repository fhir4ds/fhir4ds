@ECHO OFF
SET tooling_jar=tooling-cli-3.8.0.jar
SET input_cache_path=%~dp0input-cache
SET mat_bundle_dir=bundles\mat

SET JAVA_TOOL_OPTIONS=-Dfile.encoding=UTF-8

IF EXIST "%input_cache_path%\%tooling_jar%" (
	ECHO running: JAVA -jar "%input_cache_path%\%tooling_jar%" -ExtractMatBundle %mat_bundle_dir% -dir
	JAVA -jar "%input_cache_path%\%tooling_jar%" -ExtractMatBundle %mat_bundle%
) ELSE If exist "..\%tooling_jar%" (
	ECHO running: JAVA -jar "..\%tooling_jar%" -ExtractMatBundle %mat_bundle_dir% -dir
	JAVA -jar "..\%tooling_jar%" -ExtractMatBundle %mat_bundle%
) ELSE (
	ECHO Tooling JAR NOT FOUND in input-cache or parent folder.  Please run _updateCQFTooling.  Aborting...
)

PAUSE
