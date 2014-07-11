import re

from django.conf import settings
from importlib import import_module


def get_api_endpoints():
    """
    Examines all views and returns those with is_api_endpoint set
    to true (done by the @api_endpoint decorator).

    TODO: this isn't particularly expensive now, but if the number of urls
    grows a lot, it may be worth caching this somewhere.
    """
    urlconf = import_module(settings.ROOT_URLCONF)
    urllist = urlconf.urlpatterns
    api_endpoints = {}
    for (url, callback) in get_all_urls(urllist):
        if getattr(callback, 'is_api_endpoint', False):
            clean_url = clean_api_regex(url)
            api_endpoints[clean_url] = callback
    return api_endpoints


def format_api_docstring(docstring):
    """
    Cleans up a python method docstring for human consumption.
    """
    if not isinstance(docstring, basestring):
        return "INVALID DOCSTRING"
    whitespace_regex = '\s+'
    ret = re.sub(whitespace_regex, ' ', docstring)
    ret = ret.strip()
    return ret


def clean_api_regex(url):
    """
    Given a django-style url regex pattern, strip it down to a human-readable
    url.

    TODO: If pks ever appear in the url, this will need to account for that.
    """
    url = url.replace('^', '')
    url = url.replace('$', '')
    if not url.startswith('/'):
        url = '/' + url
    return url


def get_all_urls(urllist, prefix=''):
    """
    Recursive generator that traverses entire tree of urls, starting with
    urllist, yielding a tuple of (url_pattern, view_function) for each
    one.
    """
    for entry in urllist:
        if hasattr(entry, 'url_patterns'):
            for url in get_all_urls(entry.url_patterns,
                                    prefix + entry.regex.pattern):
                yield url
        else:
            yield (prefix + entry.regex.pattern, entry.callback)
