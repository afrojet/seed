"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
from annoying.decorators import ajax_request
from django.contrib.auth.decorators import login_required

from data_importer.models import (
    ImportFile,
    ImportRecord,
)


@ajax_request
@login_required
def handle_s3_upload_complete(request):
    """
    Handles the POST from FineUploader, sent upon upload-to-s3 complete.
    Request includes the ImportRecord id and the key from s3.
    """
    record = ImportRecord.objects.get(pk=request.REQUEST["import_record"])

    filename = request.REQUEST['key']
    source_type = request.REQUEST['source_type']

    f = ImportFile.objects.create(import_record=record,
                                  file=filename,
                                  source_type=source_type)
    return {'success': True, "import_file_id": f.pk}
