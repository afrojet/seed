"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
from django.conf import settings

if 'nose' not in settings.TEST_RUNNER:
    from .test_views import DataImporterViewTests
