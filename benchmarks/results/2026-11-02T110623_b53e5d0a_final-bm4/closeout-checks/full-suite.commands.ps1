$env:APP_PORT = '18083'
$env:MONGO_PORT = '0'
$coverageRoot = Join-Path $PSScriptRoot 'coverage'
New-Item -ItemType Directory -Force -Path $coverageRoot | Out-Null
docker build --target dev --tag mercer-closeout-tests-app-dev src
if ($LASTEXITCODE -ne 0) { throw "Full-suite dev image build exited $LASTEXITCODE" }
docker build --target runtime --tag mercer-closeout-tests-app src
if ($LASTEXITCODE -ne 0) { throw "Full-suite runtime image build exited $LASTEXITCODE" }
docker compose -p mercer-closeout-tests down --volumes
if ($LASTEXITCODE -ne 0) { throw "Full-suite reset exited $LASTEXITCODE" }
docker compose -p mercer-closeout-tests up --detach --wait db mongo
if ($LASTEXITCODE -ne 0) { throw "Full-suite services exited $LASTEXITCODE" }
docker compose -p mercer-closeout-tests run --rm migrate python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw "Full-suite migrations exited $LASTEXITCODE" }
docker compose -p mercer-closeout-tests run --rm --volume "${coverageRoot}:/reports" migrate python /app/scripts/coverage_suite.py --output /reports
$suiteCode = $LASTEXITCODE
$global:CloseoutNativeExitCode = $suiteCode
if ($suiteCode -ne 0) { return }
docker compose -p mercer-closeout-tests down --volumes
if ($LASTEXITCODE -ne 0) { throw "Full-suite cleanup exited $LASTEXITCODE" }
Remove-Item Env:APP_PORT, Env:MONGO_PORT
