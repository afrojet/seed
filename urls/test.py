"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
from django.conf.urls import patterns, include, url

urlpatterns = patterns(
    '',
    url(r'^main/', include('urls.main')),
)
