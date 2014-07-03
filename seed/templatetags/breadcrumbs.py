"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
#!/usr/bin/env python
# encoding: utf-8
"""
breadcrumbs.py

https://bitbucket.org/Mathiasdm/django-simple-breadcrumbs/
"""

from django import template
from django.template import Node, Variable
from django.utils.encoding import smart_unicode
from django.template.defaulttags import url
from django.template import VariableDoesNotExist
from django.utils.translation import ugettext as _


register = template.Library()


def create_crumb(title, url=None):
    """
    Helper function
    """

    if url:
        crumb = '<span class="breadcrumb-separator">/</span><a class="breadcrumb-item" href="%s">%s</a>' % (url, title)
    else:
        crumb = '<span class="breadcrumb-separator">/</span><span class="breadcrumb-item">%s</span>' % (title, )

    return crumb


def create_crumb_first(title, url=None):
    """
    Helper function
    """

    if url:
        crumb = '<a class="breadcrumb-item root" href="%s">%s</a>' % (url, title)
    else:
        crumb = '<span class="breadcrumb-item root">%s</span>' % (title, )

    return crumb


@register.tag
def breadcrumb(parser, token):
    """
    Renders the breadcrumb.
    Examples:
        {% breadcrumb "Title of breadcrumb" url_var %}
        {% breadcrumb context_var  url_var %}
        {% breadcrumb "Just the title" %}
        {% breadcrumb just_context_var %}

    Parameters:
    -First parameter is the title of the crumb,
    -Second (optional) parameter is the url variable to link to, produced by url tag, i.e.:
        {% url "person_detail" object.id as person_url %}
        then:
        {% breadcrumb person.name person_url %}

    @author Andriy Drozdyuk
    """
    return BreadcrumbNode(token.split_contents()[1:])


@register.tag
def breadcrumb_root(parser, token):
    """
    Renders the breadcrumb.
    Examples:
        {% breadcrumb "Title of breadcrumb" url_var %}
        {% breadcrumb context_var  url_var %}
        {% breadcrumb "Just the title" %}
        {% breadcrumb just_context_var %}

    Parameters:
    -First parameter is the title of the crumb,
    -Second (optional) parameter is the url variable to link to, produced by url tag, i.e.:
        {% url "person_detail/" object.id as person_url %}
        then:
        {% breadcrumb person.name person_url %}

    @author Andriy Drozdyuk
    """
    return BreadcrumbNode(token.split_contents()[1:], create_crumb_first)


@register.tag
def breadcrumb_url(parser, token):
    """
    Same as breadcrumb
    but instead of url context variable takes in all the
    arguments URL tag takes.
        {% breadcrumb "Title of breadcrumb" person_detail person.id %}
        {% breadcrumb person.name person_detail person.id %}
    """

    bits = token.split_contents()
    if len(bits)==2:
        return breadcrumb(parser, token)

    # Extract our extra title parameter
    title = bits.pop(1)
    token.contents = ' '.join(bits)

    url_node = url(parser, token)

    return UrlBreadcrumbNode(title, url_node)


@register.tag
def breadcrumb_url_root(parser, token):
    """
    Same as breadcrumb
    but instead of url context variable takes in all the
    arguments URL tag takes.
        {% breadcrumb "Title of breadcrumb" person_detail person.id %}
        {% breadcrumb person.name person_detail person.id %}
    """

    bits = token.split_contents()
    if len(bits) == 2:
        return breadcrumb(parser, token)

    # Extract our extra title parameter
    title = bits.pop(1)
    token.contents = ' '.join(bits)

    url_node = url(parser, token)

    return UrlBreadcrumbNode(title, url_node, create_crumb_first)


class BreadcrumbNode(Node):
    def __init__(self, vars, render_func=create_crumb):
        """
        First var is title, second var is url context variable
        """
        self.vars = map(Variable, vars)
        self.render_func = render_func

    def render(self, context):
        title = self.vars[0].var

        if title.find("'") == -1 and title.find('"') == -1:
            try:
                val = self.vars[0]
                title = val.resolve(context)
            except:
                title = ''

        else:
            title = title.strip("'").strip('"')
            title = smart_unicode(title)

        url = None

        if len(self.vars) > 1:
            val = self.vars[1]
            try:
                url = val.resolve(context)
            except VariableDoesNotExist:
                print 'URL does not exist', val
                url = None

        # add ugettext function for title i18n translation
        title = _(title)
        return self.render_func(title, url)


class UrlBreadcrumbNode(Node):
    def __init__(self, title, url_node, render_func=create_crumb):
        self.title = Variable(title)
        self.url_node = url_node
        self.render_func = render_func

    def render(self, context):
        title = self.title.var

        if title.find("'") == -1 and title.find('"') == -1:
            try:
                val = self.title
                title = val.resolve(context)
            except:
                title = ''
        else:
            title = title.strip("'").strip('"')
            title = smart_unicode(title)

        url = self.url_node.render(context)
        # add ugettext function for title translation i18n
        title = _(title)
        return self.render_func(title, url)
