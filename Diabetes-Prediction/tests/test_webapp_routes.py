import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from webapp.app import app


class TestWebappRoutes(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_public_routes_render(self):
        for route in ["/", "/login", "/register"]:
            response = self.client.get(route)
            self.assertIn(response.status_code, (200, 302))

    def test_protected_routes_redirect_to_login(self):
        response = self.client.get("/about", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
