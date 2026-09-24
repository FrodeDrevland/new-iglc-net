<#
.SYNOPSIS
  Count pages and export PDFs of IGLC papers with Microsoft Word (Windows, Word installed).

.DESCRIPTION
  Word is the only program that lays out the papers exactly as the authors see them, so page
  counts and the final PDFs come from Word. For every .docx in -InputFolder this script opens
  the file (invisibly, read-only), updates its fields, and writes:
    - pages.csv with the file name and Word's page count
    - with -Pdf: <name>.pdf in -OutputFolder

.EXAMPLE
  # Page counts of the edited papers, before page numbers are assigned
  .\tools\word_batch.ps1 -InputFolder "C:\IGLC35\edited"

.EXAMPLE
  # PDFs of the papers after the system has written headers, footers and page numbers
  .\tools\word_batch.ps1 -InputFolder "C:\IGLC35\stamped" -OutputFolder "C:\IGLC35\pdf" -Pdf
#>
param(
    [Parameter(Mandatory = $true)] [string] $InputFolder,
    [string] $OutputFolder = $InputFolder,
    [switch] $Pdf
)

$ErrorActionPreference = "Stop"
$wdStatisticPages = 2
$wdExportFormatPDF = 17
$wdExportOptimizeForPrint = 0
$wdExportCreateHeadingBookmarks = 1

New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null
$files = Get-ChildItem -Path $InputFolder -Filter *.docx | Where-Object { $_.Name -notlike '~$*' } |
    Sort-Object { [int]($_.BaseName -replace '\D', '0') }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$rows = @()
try {
    $i = 0
    foreach ($file in $files) {
        $i++
        Write-Progress -Activity "Word" -Status $file.Name -PercentComplete (100 * $i / $files.Count)
        $doc = $word.Documents.Open($file.FullName, $false, $true, $false)
        try {
            $doc.Fields.Update() | Out-Null
            foreach ($section in $doc.Sections) {
                foreach ($part in @($section.Headers + $section.Footers)) { $part.Range.Fields.Update() | Out-Null }
            }
            $doc.Repaginate()
            $pages = $doc.ComputeStatistics($wdStatisticPages)
            if ($Pdf) {
                $target = Join-Path $OutputFolder ($file.BaseName + ".pdf")
                $doc.ExportAsFixedFormat($target, $wdExportFormatPDF, $false, $wdExportOptimizeForPrint,
                    0, 0, 0, 0, $true, $true, $wdExportCreateHeadingBookmarks, $true, $true, $false)
            }
            $rows += [pscustomobject]@{ file = $file.Name; pages = $pages }
            Write-Host ("{0,-12} {1,3} pages" -f $file.Name, $pages)
        }
        finally {
            $doc.Close([ref]0)
        }
    }
}
finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
$csv = Join-Path $OutputFolder "pages.csv"
$rows | Export-Csv -Path $csv -NoTypeInformation -Encoding UTF8
Write-Host "Page counts written to $csv"
