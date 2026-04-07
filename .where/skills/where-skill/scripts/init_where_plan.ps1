param(
  [string]$PlanPath = '.where-agent-progress.md',
  [string]$Title = 'Where Plan',
  [switch]$WithExampleIds
)

if (Test-Path $PlanPath) {
  Write-Output "Plan file already exists: $PlanPath"
  exit 0
}

$line1 = '- [~] Establish plan baseline'
$line2 = '  - [ ] Confirm scope with user'
$line3 = '- [ ] Implement next task'
$line4 = '- [!] Blocked task (reason: waiting for dependency)'
$line5 = '- [x] Completed task'

if ($WithExampleIds) {
  $line1 = "$line1 <!-- where:id:where-001 -->"
  $line2 = "$line2 <!-- where:id:where-001-a -->"
  $line3 = "$line3 <!-- where:id:where-002 -->"
  $line4 = "$line4 <!-- where:id:where-003 -->"
  $line5 = "$line5 <!-- where:id:where-004 -->"
}

$template = @(
  "# Plan: $Title",
  $line1,
  $line2,
  $line3,
  $line4,
  $line5
) -join "`r`n"

$template | Set-Content -Encoding UTF8 $PlanPath
Write-Output "Created: $PlanPath"
