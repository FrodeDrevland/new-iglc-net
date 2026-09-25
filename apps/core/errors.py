"""Error reports (the mails to DJANGO_ADMINS and the debug page) without secrets.

Django hides settings whose names contain KEY, SECRET, PASS, TOKEN and the like, but not
connection strings: the storage account's (AZURE_STORAGE_CONNECTION_STRING, and inside STORAGES)
holds its access key. This filter hides those too.
"""

import re

from django.views.debug import SafeExceptionReporterFilter


class ReporterFilter(SafeExceptionReporterFilter):
    hidden_settings = re.compile(
        "API|AUTH|TOKEN|KEY|SECRET|PASS|SIGNATURE|HTTP_COOKIE|CONNECTION|DSN|CREDENTIAL", flags=re.I)
