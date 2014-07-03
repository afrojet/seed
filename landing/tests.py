"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
from django.test.utils import override_settings
from django.test import TestCase, Client
from django.core.urlresolvers import reverse
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from landing.models import SEEDUser as User
import random, string, sys

from unittest import skip

class UserLoginTest(TestCase):
    def setUp(self):
        self.email = "%s@example.com" % \
		''.join([random.choice(string.lowercase) for x in range(16)])
        self.password = ''.join([random.choice(string.lowercase) for x in range(16)])
        self.user = User.objects.create_user(
            username=self.email,
            email=self.email,
            password=self.password)

    @skip('Model Changes 02/12/2014')
    def test_successfulLogin(self):
        loginURL = reverse('landing:login')
        client = Client()
        response = client.post(loginURL, {'email': self.email,
                                          'password': self.password }, secure=True)
        assert '_auth_user_id' in client.session

    @skip('Model Changes 02/12/2014')
    def test_failedLogin(self):
        loginURL = reverse('landing:login')
        client = Client()
        response = client.post(loginURL, {'email': self.email, 
	                                  'password': 'ibebroken' }, secure=True)
        assert not '_auth_user_id' in client.session

    def tearDown(self):
        self.user.delete()

class UserSetupTest(TestCase):
    @skip('Model Changes 02/12/2014')
    def test_successfulUserSetup(self):
        email = "%s@example.com" % \
                ''.join([random.choice(string.lowercase) for x in range(16)])
        password = ''.join([random.choice(string.lowercase) for x in range(16)])
        user = User.objects.create_user(username=email, email=email)
        old_pw = user.password
        token = default_token_generator.make_token(user)
        signupURL = reverse("landing:signup", kwargs={
            'uidb64': urlsafe_base64_encode(force_bytes(user.pk)), "token":token })
        
        client = Client()
        response = client.post(signupURL, { "new_password1": password,
                                            "new_password2": password })

        user = User.objects.get(pk=user.pk)
        assert user.password != old_pw
        user.delete()

    @skip('Model Changes 02/12/2014')
    def test_failedUserSetup(self):
        email = "%s@example.com" % \
                ''.join([random.choice(string.lowercase) for x in range(16)])
        password = ''.join([random.choice(string.lowercase) for x in range(16)])
        user = User.objects.create_user(username=email, email=email)
        old_pw = user.password
        token = default_token_generator.make_token(user)
        signupURL = reverse("landing:signup", kwargs={
            'uidb64': urlsafe_base64_encode(force_bytes(user.pk)), "token":token })

        client = Client()
        response = client.post(signupURL, { "new_password1": password,
                                            "new_password2": "ibebroken" })

        user = User.objects.get(pk=user.pk)
        assert user.password == old_pw
        user.delete()

