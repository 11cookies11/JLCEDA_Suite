param(
  [string]$PlanPath = '.where-agent-progress.md'
)

if (-not (Test-Path $PlanPath)) {
  Write-Error "Plan file not found: $PlanPath"
  exit 1
}

$raw = Get-Content -Raw -Encoding UTF8 $PlanPath
$lines = $raw -split "`r?`n"
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

if ($lines.Count -eq 0 -or -not $lines[0].StartsWith('# Plan: ')) {
  $errors.Add('Line 1 must start with "# Plan: ".')
}

$taskRegex = '^( *)(- \[( |~|!|x)\] .+)$'
$taskIndentStack = New-Object System.Collections.Generic.List[int]
$inProgressCount = 0

for ($i = 0; $i -lt $lines.Count; $i++) {
  $lineNumber = $i + 1
  $line = $lines[$i]

  if ($line -match "`t") {
    $errors.Add("Line $lineNumber contains a tab character; use spaces only.")
  }

  if ($line.Trim().Length -eq 0 -or $line.StartsWith('# ')) {
    continue
  }

  if ($line -notmatch '^\s*- ') {
    $warnings.Add("Line $lineNumber is non-task content: '$line'")
    continue
  }

  if ($line -notmatch $taskRegex) {
    $errors.Add("Line $lineNumber is not a valid task line: '$line'")
    continue
  }

  $indent = $matches[1].Length
  $content = $matches[2]

  if ($indent % 2 -ne 0) {
    $errors.Add("Line $lineNumber has odd indentation ($indent spaces); use 2-space levels.")
  }

  if ($content -like '*[~]*') {
    $inProgressCount++
  }

  while ($taskIndentStack.Count -gt 0 -and $taskIndentStack[$taskIndentStack.Count - 1] -ge $indent) {
    $taskIndentStack.RemoveAt($taskIndentStack.Count - 1)
  }

  if ($taskIndentStack.Count -gt 0) {
    $expectedMaxIndent = $taskIndentStack[$taskIndentStack.Count - 1] + 2
    if ($indent -gt $expectedMaxIndent) {
      $errors.Add("Line $lineNumber skips indentation levels (indent=$indent, expected <= $expectedMaxIndent).")
    }
  } elseif ($indent -ne 0) {
    $errors.Add("Line $lineNumber starts indented without a parent task.")
  }

  $taskIndentStack.Add($indent)
}

if ($inProgressCount -eq 0) {
  $warnings.Add('No [~] in-progress task found.')
}
if ($inProgressCount -gt 1) {
  $warnings.Add("Multiple [~] in-progress tasks found: $inProgressCount")
}

if ($errors.Count -gt 0) {
  Write-Output 'Where Plan Validation: FAILED'
  $errors | ForEach-Object { Write-Output "ERROR: $_" }
  if ($warnings.Count -gt 0) {
    $warnings | ForEach-Object { Write-Output "WARN: $_" }
  }
  exit 1
}

Write-Output 'Where Plan Validation: PASSED'
if ($warnings.Count -gt 0) {
  $warnings | ForEach-Object { Write-Output "WARN: $_" }
}
exit 0
