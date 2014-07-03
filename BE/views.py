"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
from django.http import HttpResponse
from django.conf import settings


def robots_txt(request, allow=False):
    try:
        if settings.ENV.lower() != "production":
            return HttpResponse(
                "User-agent: *\nDisallow: /", mimetype="text/plain"
            )
        else:
            return HttpResponse(
                "User-agent: *\nAllow: /", mimetype="text/plain"
            )
    except:
        pass
    if allow:
        return HttpResponse("User-agent: *\nAllow: /", mimetype="text/plain")
    else:
        return HttpResponse(
            "User-agent: *\nDisallow: /", mimetype="text/plain"
        )
