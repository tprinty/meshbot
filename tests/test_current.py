"""Unit tests for the current-conditions module.

Runs without a Meshtastic device or network access — all HTTP calls mocked.
"""

import unittest
from unittest.mock import MagicMock, patch


def _resp(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _points_response(stations_url):
    return {"properties": {"observationStations": stations_url}}


def _stations_response(station_id):
    return {"features": [{"properties": {"stationIdentifier": station_id}}]}


def _observation_response(
    temp_c, heat_index_c=None, humidity=None, desc="Clear"
):
    props = {
        "temperature": {"value": temp_c},
        "textDescription": desc,
    }
    if heat_index_c is not None:
        props["heatIndex"] = {"value": heat_index_c}
    if humidity is not None:
        props["relativeHumidity"] = {"value": humidity}
    return {"properties": props}


class TestCurrentConditions(unittest.TestCase):

    def _make(self):
        from modules.current import CurrentConditions
        return CurrentConditions(30.6954, -88.0399)

    def _mock_chain(self, mock_get, observation_json):
        """Mock the three-request NWS chain: points -> stations -> latest."""
        mock_get.side_effect = [
            _resp(json_data=_points_response("http://stations")),
            _resp(json_data=_stations_response("KMOB")),
            _resp(json_data=observation_json),
        ]

    @patch("modules.current.requests.get")
    def test_reports_temp_and_heat_index(self, mock_get):
        self._mock_chain(
            mock_get,
            _observation_response(temp_c=31, heat_index_c=37.7, humidity=70.5),
        )
        result = self._make().get_current()
        # 31 C = 88 F, 37.7 C = 100 F
        self.assertIn("88°F", result)
        self.assertIn("feels 100°F", result)
        self.assertIn("70%", result)
        self.assertIn("Clear", result)

    @patch("modules.current.requests.get")
    def test_reports_temp_without_heat_index(self, mock_get):
        # NWS omits heatIndex when it is not hot enough to compute one.
        self._mock_chain(
            mock_get,
            _observation_response(temp_c=10, heat_index_c=None, humidity=None),
        )
        result = self._make().get_current()
        # 10 C = 50 F
        self.assertIn("50°F", result)
        self.assertNotIn("feels", result)

    @patch("modules.current.requests.get")
    def test_points_request_failure(self, mock_get):
        mock_get.return_value = _resp(status_code=503)
        result = self._make().get_current()
        self.assertIn("Failed", result)

    @patch("modules.current.requests.get")
    def test_no_stations(self, mock_get):
        mock_get.side_effect = [
            _resp(json_data=_points_response("http://stations")),
            _resp(json_data={"features": []}),
        ]
        result = self._make().get_current()
        self.assertIn("Failed", result)

    @patch("modules.current.requests.get")
    def test_missing_temperature(self, mock_get):
        self._mock_chain(mock_get, {"properties": {"temperature": {}}})
        result = self._make().get_current()
        self.assertIn("Failed", result)

    @patch("modules.current.requests.get")
    def test_connection_error_is_caught(self, mock_get):
        mock_get.side_effect = ConnectionError("boom")
        result = self._make().get_current()
        self.assertIn("Failed", result)

    def test_celsius_to_fahrenheit(self):
        from modules.current import CurrentConditions
        self.assertEqual(CurrentConditions._c_to_f(0), 32)
        self.assertEqual(CurrentConditions._c_to_f(100), 212)
        self.assertEqual(CurrentConditions._c_to_f(37.7), 100)


if __name__ == "__main__":
    unittest.main()
