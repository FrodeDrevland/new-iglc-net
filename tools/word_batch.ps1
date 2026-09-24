<#
.SYNOPSIS
  Count pages and export PDFs of IGLC papers with Microsoft Word (Windows, Word installed).

.DESCRIPTION
  Word is the only program that lays out the papers exactly as the authors see them, so page
  counts and the final PDFs come from Word. For every .docx in -InputFolder this script opens
  the file (invisibly), closes it again without saving, and writes:
    - pages.csv with the file name and Word's page count (and with -Pdf, the PDF's)
    - with -Pdf: <name>.pdf in -OutputFolder
  Word's PDF export can lay a paper out differently from Word's own screen (one IGLC 34 paper
  was 12 pages in Word and 13 in the PDF). With -Pdf, such papers are listed at the end: adjust
  them in Word (for example tighten the text before the extra page break) and run again.

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
        # Opened the plain way: the read-only open with extra options made Word hang when
        # saving the PDF. The file is closed without saving, so it is not changed.
        $doc = $word.Documents.Open([string]$file.FullName)
        try {
            # No field updates: page numbers in headers and footers are filled in when Word lays
            # out the pages, and updating the body's fields (citations, cross-references) could
            # change the paper or make Word wait for an add-in.
            Write-Host " counting..." -NoNewline
            $pages = $doc.ComputeStatistics($wdStatisticPages)
            if ($Pdf) {
                Write-Host " pdf..." -NoNewline
                $target = Join-Path $OutputFolder ($file.BaseName + ".pdf")
                # Save as PDF (format 17) with Word's own exporter. Only the two arguments: the
                # long ExportAsFixedFormat call hung when made from PowerShell.
                $doc.SaveAs2([string]$target, 17)
                # Count the PDF's pages ("/Type /Page" objects; exact for Word's PDFs)
                $text = [System.Text.Encoding]::GetEncoding(28591).GetString([System.IO.File]::ReadAllBytes($target))
                $pdfPages = ([regex]::Matches($text, '/Type\s*/Page(?![a-zA-Z])')).Count
            }
            else { $pdfPages = $null }
            $rows += [pscustomobject]@{ file = $file.Name; pages = $pages; pdf_pages = $pdfPages }
            if ($pdfPages -and $pdfPages -ne $pages) {
                Write-Host (" {0,3} pages, but the PDF has {1}!" -f $pages, $pdfPages) -ForegroundColor Yellow
            }
            else { Write-Host (" {0,3} pages" -f $pages) }
        }
        finally {
            $doc.Close(0)  # 0 = do not save
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
$differ = $rows | Where-Object { $_.pdf_pages -and $_.pdf_pages -ne $_.pages }
if ($differ) {
    Write-Host ""
    Write-Host "These PDFs have a different number of pages than Word shows; adjust the papers and run again:" -ForegroundColor Yellow
    $differ | ForEach-Object { Write-Host ("  {0}: Word {1}, PDF {2}" -f $_.file, $_.pages, $_.pdf_pages) -ForegroundColor Yellow }
}
