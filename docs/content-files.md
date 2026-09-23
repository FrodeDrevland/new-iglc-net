# Files from the old /Content/ folder

The old site served some files straight from its own `Content` folder. They move to a blob container,
`content` in the `iglcstorage` account, next to the paper PDFs. The new site redirects
`/Content/<path>` to `https://iglcstorage.blob.core.windows.net/content/<path>` (setting `LEGACY_CONTENT_URL`).

| Folder | Files | Size | Used by |
| --- | --- | --- | --- |
| `Proceedings/` | full proceedings PDFs, 2015 to 2024 | 536 MB | Full proceedings page |
| `Documents/` | standards, author templates and forms | 9.5 MB | Standards and For authors pages |
| `Images/` | images on content pages | 6.1 MB | Formatting requirements, Sven Bertelsen pages |

## Upload (once, with the Azure CLI)

Run in PowerShell after `az login`. The paths inside the container must match the old paths exactly,
because blob storage is case-sensitive.

```powershell
$src = "C:\Users\frode\My Drive (frode@drevcon.com)\80. Koding\Visual Studio\IGLC\IGLC\Content"
az storage container create --account-name iglcstorage --name content --public-access blob --auth-mode login
foreach ($folder in "Proceedings", "Documents", "Images") {
    az storage blob upload-batch --account-name iglcstorage --auth-mode login `
        --destination content --destination-path $folder --source "$src\$folder" --overwrite
}
```

`--auth-mode login` needs the Storage Blob Data Contributor role on the account. Without it, use
`--account-key` with a key from the Azure portal instead (never put the key in a file in this repository).

## Check

```powershell
.venv\Scripts\python tools\url_inventory.py check inventory\recheck-report.csv --base http://127.0.0.1:8000 --out inventory\recheck-report-2.csv
```

The `/Content/...` URLs should now pass; only the links that were already broken on the old site should fail.

## Full proceedings and ZIPs on conference pages

The old conference pages looked up two other blob containers on every visit: `proceedings`
(files named `Proceedings-IGLC<number>...pdf`) and `papers-zipped` (`IGLC<number>_Papers.zip`).
The new site stores these links on each conference instead. To fill them in, list the files and load the list:

```powershell
$key = az storage account keys list --account-name iglcstorage --query "[0].value" -o tsv
$files = foreach ($c in "proceedings", "papers-zipped") {
    az storage blob list --account-name iglcstorage --account-key $key --container-name $c --query "[].name" -o tsv |
        ForEach-Object { "https://iglcstorage.blob.core.windows.net/$c/$_" }
}
$files | Set-Content inventory\blob-files.txt
.venv\Scripts\python manage.py link_blob_files inventory\blob-files.txt
```

On the preview server, copy `blob-files.txt` to `/mnt/user/appdata/iglc/import/` and run
`docker exec iglc-web python manage.py link_blob_files /import/blob-files.txt`.
The links can also be edited by hand on each conference in the archive admin.
