from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import database.connection as db_connection
from services.short_links import (
    create_short_link,
    delete_short_link_by_url,
    get_vless_by_code,
)
from shortener_app import open_short_link


class ShortLinksTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.original_db_path = db_connection.DB_PATH
        self.original_pragmas_initialized = (
            db_connection._DATABASE_PRAGMAS_INITIALIZED
        )
        db_connection.DB_PATH = Path(self.temp_dir.name) / "bot.db"
        db_connection._DATABASE_PRAGMAS_INITIALIZED = False

    def tearDown(self):
        db_connection.DB_PATH = self.original_db_path
        db_connection._DATABASE_PRAGMAS_INITIALIZED = (
            self.original_pragmas_initialized
        )
        self.temp_dir.cleanup()

    def test_short_link_is_saved_reused_and_rendered_as_html(self):
        vless_link = (
            "vless://00000000-0000-4000-8000-000000000000@example.com:443"
            "?type=tcp&security=reality#test"
        )

        short_url = create_short_link(
            vless_link,
            base_url="https://golum.shop:8443",
        )
        duplicate_short_url = create_short_link(
            vless_link,
            base_url="https://golum.shop:8443",
        )
        code = short_url.rsplit("/", 1)[-1]

        self.assertEqual(len(code), 8)
        self.assertEqual(short_url, duplicate_short_url)
        self.assertEqual(get_vless_by_code(code), vless_link)

        response = open_short_link(code)
        body = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertNotIn("location", response.headers)
        self.assertIn("Скопировать", body)
        self.assertIn("Открыть VPN", body)
        self.assertIn("copyKey(false)", body)
        self.assertIn("vless://", body)

        delete_short_link_by_url(vless_link)
        self.assertIsNone(get_vless_by_code(code))

    def test_invalid_code_returns_400(self):
        response = open_short_link("bad code with spaces")

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
