import base64
import io
import unittest

from PIL import Image
from pydantic import ValidationError

from engine.api.schemas import BuildCreate, WebFeatures


def png_data_url_bytes(size=(128, 128)):
    image = Image.new("RGBA", size, (40, 80, 180, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class BuildSchemaTests(unittest.TestCase):
    def valid_android(self, **overrides):
        payload = {
            "platform": "android",
            "app_name": "Example Portal",
            "package_id": "com.example.portal",
            "website_url": "https://example.com",
            "formats": ["apk", "aab"],
            "features": {"launcher_icon": True, "app_icon_png_base64": png_data_url_bytes()},
        }
        payload.update(overrides)
        return payload

    def test_accepts_valid_android_request(self):
        result = BuildCreate.model_validate(self.valid_android())
        self.assertEqual(result.platform, "android")
        self.assertEqual(result.formats, ["apk", "aab"])

    def test_rejects_non_https_website(self):
        with self.assertRaises(ValidationError):
            BuildCreate.model_validate(self.valid_android(website_url="http://example.com"))

    def test_canonicalizes_hostname_case_and_trailing_dot(self):
        result = BuildCreate.model_validate(self.valid_android(website_url="https://EXAMPLE.com./portal/"))
        self.assertEqual(result.website_url, "https://example.com/portal")

    def test_rejects_single_label_hostname(self):
        with self.assertRaises(ValidationError):
            BuildCreate.model_validate(self.valid_android(website_url="https://intranet/"))

    def test_rejects_ipa_for_android(self):
        with self.assertRaises(ValidationError):
            BuildCreate.model_validate(self.valid_android(formats=["ipa"]))

    def test_ios_requires_ipa_only(self):
        payload = self.valid_android(platform="ios", formats=["apk"])
        with self.assertRaises(ValidationError):
            BuildCreate.model_validate(payload)

    def test_rejects_invalid_application_identifier(self):
        with self.assertRaises(ValidationError):
            BuildCreate.model_validate(self.valid_android(package_id="com.example.bad-name"))

    def test_rejects_non_square_icon(self):
        with self.assertRaises(ValidationError):
            WebFeatures.model_validate({"app_icon_png_base64": png_data_url_bytes((128, 64))})

    def test_rejects_unknown_feature_fields(self):
        with self.assertRaises(ValidationError):
            WebFeatures.model_validate({"disable_all_security": True})


if __name__ == "__main__":
    unittest.main()
