"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
#!/usr/bin/env python
# encoding: utf-8
"""
urls.py

Copyright (c) 2013 Building Energy. All rights reserved.
"""

from django.conf.urls import patterns, url


urlpatterns = patterns(
    'data_importer.views',
    url(
        r's3_upload_complete$',
        'handle_s3_upload_complete',
        name='s3_upload_complete'
    ),
)
