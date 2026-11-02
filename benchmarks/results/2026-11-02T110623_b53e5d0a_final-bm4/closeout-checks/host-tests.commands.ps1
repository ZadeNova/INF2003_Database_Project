$taskRoot = $PSScriptRoot
$tempPath = [IO.Path]::GetFullPath((Join-Path $taskRoot 'host-tests-temp'))
$boundary = [IO.Path]::GetFullPath($taskRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $tempPath.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) { throw 'Host test temp path escaped the verified task directory' }
python -m pytest --noconftest -q -rs -p no:cacheprovider --basetemp $tempPath --junitxml (Join-Path $taskRoot 'host.xml') tests/test_check_docs.py tests/test_package_submission.py tests/test_request_timing.py
if ($LASTEXITCODE -ne 0) { throw "Host tests exited $LASTEXITCODE" }
@'
import json
from pathlib import Path
from xml.etree import ElementTree as ET
p=Path('.cache/benchmark-close-out/host.xml')
counts={key:sum(int(s.get(key,0)) for s in ET.parse(p).getroot().iter('testsuite')) for key in ('tests','failures','errors','skipped')}
print(json.dumps(counts))
assert counts['tests']>0 and counts['skipped']==counts['failures']==counts['errors']==0
'@ | python -
if ($LASTEXITCODE -ne 0) { throw 'Host test results must contain no skips, failures or errors' }
