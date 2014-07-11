"""
:copyright: (c) 2014 Building Energy Inc
:license: see LICENSE for more details.
"""
from salad.steps.everything import *
from lettuce import step
from test_helpers import Factory
from django.core.urlresolvers import reverse


@step(u'I visit the home page')
def i_visit_the_home_page(step):
    world.browser.visit(django_url(reverse("seed:home")))


@step(u'I go to the jasmine unit tests for the SEED')
def given_i_go_to_the_jasmine_unit_tests_for_the_SEED(step):
    world.browser.visit(django_url(reverse("seed:angular_js_tests")))


@step(u'I should see that the tests passed')
def then_i_should_see_that_the_tests_passed(step):
    time.sleep(2)
    try:
        assert world.browser.is_element_present_by_css(".passingAlert.bar")
    except:
        time.sleep(50)
        assert len(world.browser.find_by_css(".passingAlert.bar")) > 0
