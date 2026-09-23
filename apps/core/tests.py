from django.test import TestCase, override_settings


class HealthCheckTests(TestCase):
    def test_healthz_ignores_host_header(self):
        response = self.client.get("/healthz", HTTP_HOST="169.254.130.4:8000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok\n")


class HostRedirectTests(TestCase):
    @override_settings(HOST_REDIRECTS={"iglc.net": "www.iglc.net"}, ALLOWED_HOSTS=["iglc.net", "www.iglc.net"])
    def test_apex_goes_to_www(self):
        from django.test import Client

        response = Client(HTTP_HOST="iglc.net").get("/papers/details/2150?x=1")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://www.iglc.net/papers/details/2150?x=1")
