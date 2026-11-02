$reports = $PSScriptRoot
docker compose -p mercer-bench-closeout-fixture --profile bench run --rm --volume "${reports}:/reports" bench-runner pytest -c /dev/null --rootdir=/app/benchmarks -q -p no:cacheprovider --junitxml=/reports/fixture.xml /app/benchmarks/tests
$testCode = $LASTEXITCODE
$global:CloseoutNativeExitCode = $testCode
if ($testCode -ne 0) { return }
docker compose -p mercer-bench-closeout-fixture --profile bench down --volumes
if ($LASTEXITCODE -ne 0) { throw "Fixture cleanup exited $LASTEXITCODE" }
