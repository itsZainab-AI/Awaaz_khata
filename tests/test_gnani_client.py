import unittest
from unittest.mock import Mock, patch

from backend.gnani_client import AUTO_LANGUAGE, PRISMA_MODEL, transcribe


class PrismaAutoDetectionTests(unittest.TestCase):
    def test_prisma_v3_auto_detection_sends_indic_auto_and_returns_detected_code(self):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "transcript": "தமிழ் உரை",
            "detected_language_code": "ta-IN",
        }

        with (
            patch("backend.gnani_client._api_key", return_value="test-key"),
            patch("backend.gnani_client._timeout", return_value=5),
            patch("backend.gnani_client._audio_upload", return_value=("audio.wav", b"audio", "audio/wav")),
            patch("backend.gnani_client._post", return_value=response) as post,
        ):
            result = transcribe(b"audio", language_hint=AUTO_LANGUAGE)

        self.assertEqual(str(result), "தமிழ் உரை")
        self.assertEqual(result.detected_language_code, "ta-IN")
        self.assertEqual(
            post.call_args.kwargs["data"],
            {
                "model": PRISMA_MODEL,
                "language_code": AUTO_LANGUAGE,
                "format": "transcribe",
            },
        )


if __name__ == "__main__":
    unittest.main()
