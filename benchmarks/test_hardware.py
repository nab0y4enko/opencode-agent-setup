"""Hardware evidence is allowlisted: never retain serials, hostnames or user identities."""
import unittest
from unittest import mock

import hardware


class HardwareEvidence(unittest.TestCase):
    def test_mac_hardware_is_recorded_without_identifiers(self):
        payload = {
            'SPHardwareDataType': [{'machine_name': 'Mac Studio', 'machine_model': 'Mac17,14',
                                    'chip_type': 'Apple M5 Max', 'number_processors': 'proc 18:6:12:0',
                                    'physical_memory': '128 GB', 'serial_number': 'PRIVATE',
                                    'platform_UUID': 'PRIVATE'}],
            'SPDisplaysDataType': [{'sppci_model': 'Apple M5 Max', 'sppci_cores': '40',
                                    'spdisplays_ndrvs': [{'serial': 'PRIVATE'}]}],
        }
        with mock.patch('hardware.subprocess.run') as run:
            import json
            run.return_value.stdout = json.dumps(payload)
            run.return_value.returncode = 0
            result = hardware.mac_hardware()
        self.assertEqual(result, {'computer': 'Mac Studio', 'model_identifier': 'Mac17,14',
                                  'chip': 'Apple M5 Max', 'cpu_description': 'proc 18:6:12:0',
                                  'memory': '128 GB', 'gpus': [{'chip': 'Apple M5 Max', 'cores': 40}]})

    def test_unavailable_or_malformed_profiler_is_explicitly_unknown(self):
        import subprocess
        for error in (OSError('missing'), subprocess.TimeoutExpired('system_profiler', 15)):
            with self.subTest(error=error), mock.patch('hardware.subprocess.run', side_effect=error):
                self.assertEqual(hardware.mac_hardware(), {'status': 'unavailable'})
        with mock.patch('hardware.subprocess.run') as run:
            run.return_value.stdout = 'malformed'
            run.return_value.returncode = 0
            self.assertEqual(hardware.mac_hardware(), {'status': 'unavailable'})

    def test_valid_json_with_invalid_hardware_shapes_is_unknown(self):
        import json
        for payload in ([], None, {'SPHardwareDataType': ['invalid']},
                        {'SPHardwareDataType': [[]]}, {'SPHardwareDataType': {}}):
            with self.subTest(payload=payload), mock.patch('hardware.subprocess.run') as run:
                run.return_value.stdout = json.dumps(payload)
                run.return_value.returncode = 0
                self.assertEqual(hardware.mac_hardware(), {'status': 'unavailable'})


if __name__ == '__main__':
    unittest.main()
