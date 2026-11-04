import contextlib
import io
import unittest
from unittest.mock import Mock, patch

from acquisition_api import AcquisitionClient, acquire_and_match, NoMatchError, main


class ApiTests(unittest.TestCase):
    def test_single_match_returns_id_and_stops_in_finally(self):
        client = Mock()
        client.poll.return_value = {}
        client.take_results.return_value = [{'identifier': 17, 'sequence': 1, 'status': 'matched'}]
        with patch('acquisition_api.AcquisitionClient', return_value=client):
            self.assertEqual(acquire_and_match(timeout_s=1), 17)
        client.start.assert_called_once()
        client.stop.assert_called_once()

    def test_unmatched_is_not_a_valid_identifier(self):
        client = Mock()
        client.poll.return_value = {}
        client.take_results.return_value = [{'identifier': None, 'sequence': 1, 'status': 'unmatched'}]
        with patch('acquisition_api.AcquisitionClient', return_value=client):
            with self.assertRaises(NoMatchError):
                acquire_and_match(timeout_s=1)
        client.stop.assert_called_once()

    def test_timeout_stops(self):
        client = Mock()
        client.take_results.return_value = []
        client.poll.return_value = {}
        with patch('acquisition_api.AcquisitionClient', return_value=client):
            with self.assertRaises(TimeoutError):
                acquire_and_match(timeout_s=.001)
        client.stop.assert_called_once()

    def test_cli_prints_only_id(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch('acquisition_api.acquire_and_match', return_value=23), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(main([]), 0)
        self.assertEqual(output.getvalue(), '23\n')
        self.assertEqual(errors.getvalue(), '')

    def test_cli_failure_has_no_success_output(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch('acquisition_api.acquire_and_match', side_effect=NoMatchError('no unique ID')), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertNotEqual(main([]), 0)
        self.assertEqual(output.getvalue(), '')
        self.assertIn('no unique ID', errors.getvalue())
