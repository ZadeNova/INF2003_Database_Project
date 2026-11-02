docker compose -p mercer-bench-closeout-fixture --profile bench down --volumes
if ($LASTEXITCODE -ne 0) { throw "Fixture down exited $LASTEXITCODE" }
docker compose -p mercer-bench-closeout-fixture --profile bench up --detach --wait bench-db bench-mongo
if ($LASTEXITCODE -ne 0) { throw "Fixture up exited $LASTEXITCODE" }
docker compose -p mercer-bench-closeout-fixture --profile bench run --rm bench-runner python -m benchmarks.load --source /app/fixtures/olist/clean
if ($LASTEXITCODE -ne 0) { throw "Fresh fixture load exited $LASTEXITCODE" }

$reports = $PSScriptRoot
docker compose -p mercer-bench-closeout-fixture --profile bench run --rm --volume "${reports}:/reports" bench-runner pytest -c /dev/null --rootdir=/app/benchmarks -q -p no:cacheprovider --junitxml=/reports/fixture-fresh.xml /app/benchmarks/tests
$testCode = $LASTEXITCODE
$global:CloseoutNativeExitCode = $testCode
if ($testCode -ne 0) { return }
docker compose -p mercer-bench-closeout-fixture --profile bench down --volumes
if ($LASTEXITCODE -ne 0) { throw "Fixture cleanup exited $LASTEXITCODE" }

