"""Regression tests for the METAR module."""

import unittest
from unittest.mock import MagicMock, patch

from modules.metar import Metar


def _make(station="KMOB"):
    return Metar(station)


class TestMetar(unittest.TestCase):

    def test_station_uppercased_and_stripped(self):
        self.assertEqual(_make(" kmob ").station, "KMOB")

    @patch("modules.metar.requests.get")
    def test_returns_raw_metar_without_marker(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "METAR KMOB 252356Z 20007KT 10SM CLR 29/24 A2997 $\n"
        mock_get.return_value = mock_resp

        result = _make().get_metar()
        self.assertEqual(
            result,
            "METAR KMOB 252356Z 20007KT 10SM CLR 29/24 A2997",
        )
        # Correct URL params requested.
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["ids"], "KMOB")
        self.assertEqual(kwargs["params"]["format"], "raw")

    @patch("modules.metar.requests.get")
    def test_non_200_returns_failure(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        self.assertEqual(
            _make().get_metar(), "Failed to fetch METAR data."
        )

    @patch("modules.metar.requests.get")
    def test_empty_body_returns_no_data(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = " $ "
        mock_get.return_value = mock_resp

        self.assertEqual(
            _make().get_metar(), "No METAR available for this station."
        )

    @patch("modules.metar.requests.get")
    def test_exception_returns_failure(self, mock_get):
        mock_get.side_effect = Exception("network down")

        self.assertEqual(
            _make().get_metar(), "Failed to fetch METAR data."
        )


if __name__ == "__main__":
    unittest.main()
