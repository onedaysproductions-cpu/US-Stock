# รันเก็บข้อมูลบนเครื่องนี้ (ใช้แทน/เสริม GitHub Actions)
# ใช้:  powershell -ExecutionPolicy Bypass -File run_local.ps1
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
New-Item -ItemType Directory -Force logs | Out-Null
$log = "logs\run_$(Get-Date -Format yyyyMMdd_HHmm).log"
if (git remote) { git pull --rebase --autostash *>> $log }
.\.venv\Scripts\python.exe capture.py *>> $log
.\.venv\Scripts\python.exe report.py *>> $log
Get-Content $log -Tail 5
