$containers = @(docker ps --format '{{.Names}}')
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify Docker containers before restoring its stopped state' }
if ($containers.Count -gt 0) { throw ('Containers remain running; leave Docker untouched: ' + ($containers -join ', ')) }
Get-Process -Name vmmem,vmmemWSL -ErrorAction SilentlyContinue | Select-Object ProcessName,Id,@{Name='WorkingSetMiB';Expression={[math]::Round($_.WorkingSet64 / 1MB,2)}} | ConvertTo-Json -Compress | Write-Output
docker desktop stop --timeout 60
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop stop exited $LASTEXITCODE" }
$runningDistros = @(wsl.exe --list --running --quiet | ForEach-Object { $_.Replace("`0",'').Trim() } | Where-Object { $_ })
if ($runningDistros -contains 'docker-desktop') {
    wsl.exe --terminate docker-desktop
    if ($LASTEXITCODE -ne 0) { throw "Docker-only WSL termination exited $LASTEXITCODE" }
}
$remainingVmmem = @(Get-Process -Name vmmem,vmmemWSL -ErrorAction SilentlyContinue)
[ordered]@{docker_stopped=$true;other_wsl_distros_untouched=$true;remaining_vmmem_processes=$remainingVmmem.Count} | ConvertTo-Json -Compress | Write-Output
