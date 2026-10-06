import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from app.server import Handler


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_health(self):
        with urllib.request.urlopen(self.url + "/health?probe=1") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response), {"status": "healthy"})
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_unknown_and_traversal_paths(self):
        for path in ("/missing", "/../../etc/passwd", "/%2e%2e/secret"):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(self.url + path)
            self.assertEqual(caught.exception.code, 404)
