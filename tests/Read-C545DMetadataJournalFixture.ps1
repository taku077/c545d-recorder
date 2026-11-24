# CI-only independent reader: never export source file contents.
param([Parameter(Mandatory=$true)][string]$JournalRoot)
$ErrorActionPreference='Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'C545DMetadataJournalPrototype.cs')
$now=[datetime]::UtcNow
$snapshot=[C545DMetadataJournalPrototype]::ReadWindow($JournalRoot,$now.AddHours(-1),$now.AddHours(1))
if($snapshot.Status -ne 'coverage_unverified' -or $snapshot.Rows.Count -ne 3 -or
    @($snapshot.Rows|Where-Object Status -eq 'profile_match_metadata_only').Count -ne 1 -or
    @($snapshot.Rows|Where-Object Status -eq 'profile_mismatch').Count -ne 1 -or
    @($snapshot.Rows|Where-Object Status -eq 'probe_unavailable').Count -ne 1){
    throw 'INDEPENDENT_JOURNAL_READER_FAILED'
}
Write-Host 'C545D_INDEPENDENT_JOURNAL_READER_PASS,rows=3,coverage_unverified=1'
