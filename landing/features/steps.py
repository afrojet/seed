"""
:copyright: (c) 2014 Building Energy Inc
:license: see LICENSE for more details.
"""
from salad.steps.everything import *
from lettuce import step
from test_helpers import Factory
from django.core.urlresolvers import reverse
import sys

@step(u'I visit the landing page')
def i_visit_the_landing_pad(step):
    world.browser.visit(django_url(reverse("landing:landing_page")))


@step(u'I should see the login prompt')
def then_i_should_see_the_login_prompt(step):
    assert len(world.browser.find_by_css(".signup_form")) > 0
