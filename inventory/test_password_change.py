from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class PasswordChangeTests(TestCase):
    old = 'Old-only-test-593!'
    new = 'New-only-test-829!'

    def setUp(self):
        self.user = get_user_model().objects.create_user('colaborador', password=self.old)
        self.other = get_user_model().objects.create_user('outra.pessoa', password=self.old)
        self.url = reverse('password_change')

    def payload(self, **extra):
        return {'old_password': self.old, 'new_password1': self.new, 'new_password2': self.new, **extra}

    def test_anonymous_cannot_access_change_or_confirmation(self):
        for url in (self.url, reverse('password_change_done')):
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertTrue(self.client.post(url, self.payload()).url.startswith('/login/'))

    def test_ordinary_user_changes_only_own_password_and_keeps_session(self):
        self.client.login(username=self.user.username, password=self.old)
        other_session = Client()
        other_session.login(username=self.user.username, password=self.old)
        self.assertContains(self.client.get(self.url), 'Salvar nova senha')
        response = self.client.post(self.url, self.payload(user_id=self.other.pk, username=self.other.username))
        self.assertRedirects(response, reverse('password_change_done'))
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new))
        self.assertFalse(self.user.check_password(self.old))
        self.assertTrue(self.other.check_password(self.old))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.assertEqual(other_session.get(self.url).status_code, 302)
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.has_perm('auth.change_user'))
        self.assertEqual(self.client.get('/admin/').status_code, 403)

    def test_invalid_passwords_leave_password_unchanged(self):
        self.client.force_login(self.user)
        for data in (self.payload(old_password='wrong'), self.payload(new_password2='different'),
                     self.payload(new_password1='123', new_password2='123')):
            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
            self.user.refresh_from_db()
            self.assertTrue(self.user.check_password(self.old))
            self.assertNotContains(response, 'value="' + self.old + '"')

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.payload()).status_code, 403)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old))

    def test_link_visible_only_when_logged_in(self):
        self.assertNotContains(self.client.get('/login/'), 'href="' + self.url + '"')
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url), 'href="' + self.url + '"')
