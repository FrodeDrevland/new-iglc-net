<#
.SYNOPSIS
  Count pages and export PDFs of IGLC papers with Microsoft Word (Windows, Word installed).

.DESCRIPTION
  Word is the only program that lays out the papers exactly as the authors see them, so page
  counts and the final PDFs come from Word. For every .docx in -InputFolder this script opens
  the file (invisibly, read-only) and writes:
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
    [switch] $Pdf,
    # Show Word while it works: use this if the script seems to hang, to see what Word is asking.
    [switch] $Visible
)

$ErrorActionPreference = "Stop"
$wdStatisticPages = 2
$wdExportFormatPDF = 17
$wdExportOptimizeForPrint = 0
$wdExportCreateHeadingBookmarks = 1

New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null
# Word runs in its own process with its own working folder: give it full paths only.
$OutputFolder = (Resolve-Path $OutputFolder).Path
$InputFolder = (Resolve-Path $InputFolder).Path
$files = Get-ChildItem -Path $InputFolder -Filter *.docx | Where-Object { $_.Name -notlike '~$*' } |
    Sort-Object { [int]($_.BaseName -replace '\D', '0') }
$word = New-Object -ComObject Word.Application
$word.Visible = [bool]$Visible
$word.DisplayAlerts = 0
$rows = @()
try {
    $i = 0
    foreach ($file in $files) {
        $i++
        Write-Progress -Activity "Word" -Status $file.Name -PercentComplete (100 * $i / $files.Count)
        Write-Host ("{0,-12} opening..." -f $file.Name) -NoNewline
        # Open(FileName, ConfirmConversions, ReadOnly, AddToRecentFiles, PasswordDocument,
        #      PasswordTemplate, Revert, WritePasswordDocument, WritePasswordTemplate, Format,
        #      Encoding, Visible, OpenAndRepair, DocumentDirection, NoEncodingDialog)
        # Empty passwords stop Word from waiting for one; NoEncodingDialog avoids another prompt.
        $doc = $word.Documents.Open($file.FullName, $false, $true, $false, "", "", $true, "", "",
            0, [Type]::Missing, [bool]$Visible, $false, [Type]::Missing, $true)
        try {
            # No field updates: page numbers in headers and footers are filled in when Word lays
            # out the pages, and updating the body's fields (citations, cross-references) could
            # change the paper or make Word wait for an add-in.
            Write-Host " counting..." -NoNewline
            $pages = $doc.ComputeStatistics($wdStatisticPages)
            if ($Pdf) {
                Write-Host " pdf..." -NoNewline
                $target = Join-Path $OutputFolder ($file.BaseName + ".pdf")
                $doc.ExportAsFixedFormat($target, $wdExportFormatPDF, $false, $wdExportOptimizeForPrint,
                    0, 0, 0, 0, $true, $true, $wdExportCreateHeadingBookmarks, $true, $true, $false)
            }
            $rows += [pscustomobject]@{ file = $file.Name; pages = $pages }
            Write-Host (" {0,3} pages" -f $pages)
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
