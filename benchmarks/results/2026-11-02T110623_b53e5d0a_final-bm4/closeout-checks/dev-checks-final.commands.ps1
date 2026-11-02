$repoRoot = (Get-Location).Path
docker build --target dev --tag mercer-bench-closeout-fixture-app-dev src
if ($LASTEXITCODE -ne 0) { throw "Dev image build exited $LASTEXITCODE" }
docker compose -p mercer-bench-closeout-fixture --profile bench run --rm --no-deps --volume "${repoRoot}:/repo" --workdir /repo bench-runner python -m ruff check --select I --fix benchmarks/resources.py benchmarks/report.py benchmarks/tests/test_reporting.py
if ($LASTEXITCODE -ne 0) { throw "Import formatting exited $LASTEXITCODE" }
docker compose -p mercer-bench-closeout-fixture --profile bench run --rm --no-deps --volume "${repoRoot}:/repo" --workdir /repo bench-runner python -m ruff format .
if ($LASTEXITCODE -ne 0) { throw "Ruff format exited $LASTEXITCODE" }
docker compose -p mercer-bench-closeout-fixture --profile bench run --rm --no-deps --volume "${repoRoot}:/repo" --workdir /repo bench-runner python -m ruff check .
if ($LASTEXITCODE -ne 0) { throw "Ruff check exited $LASTEXITCODE" }
docker compose -p mercer-bench-closeout-fixture --profile bench run --rm --no-deps --volume "${repoRoot}:/repo" --workdir /repo bench-runner python -m pytest --noconftest -c /dev/null --rootdir=/repo/benchmarks -q -p no:cacheprovider /repo/benchmarks/tests/test_reporting.py
if ($LASTEXITCODE -ne 0) { throw "Reporting regression tests exited $LASTEXITCODE" }

