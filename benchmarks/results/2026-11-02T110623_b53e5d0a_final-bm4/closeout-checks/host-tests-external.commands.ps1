$taskRoot = $PSScriptRoot
$tempPath = Join-Path ([IO.Path]::GetTempPath()) ('mercer-benchmark-host-' + [guid]::NewGuid().ToString('N'))
Write-Output "Host test temporary repositories: $tempPath"
python -m pytest --noconftest -q -rs -p no:cacheprovider --basetemp $tempPath --junitxml (Join-Path $taskRoot 'host-external.xml') tests/test_check_docs.py tests/test_package_submission.py tests/test_request_timing.py
if ($LASTEXITCODE -ne 0) { throw "Host tests exited $LASTEXITCODE" }
