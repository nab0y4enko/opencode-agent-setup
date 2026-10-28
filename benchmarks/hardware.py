"""Privacy-safe hardware facts for benchmark reports."""
import json
import subprocess


def mac_hardware():
    """Keep only hardware characteristics, never the full profiler payload."""
    try:
        result = subprocess.run(['system_profiler', 'SPHardwareDataType', 'SPDisplaysDataType', '-json'],
                                capture_output=True, text=True, timeout=15, check=False)
        if result.returncode:
            return {'status': 'unavailable'}
        data = json.loads(result.stdout)
        overview = data['SPHardwareDataType'][0]
        if not isinstance(overview, dict):
            return {'status': 'unavailable'}
        fields = {'computer': 'machine_name', 'model_identifier': 'machine_model', 'chip': 'chip_type',
                  'cpu_description': 'number_processors', 'memory': 'physical_memory'}
        facts = {key: overview.get(source) for key, source in fields.items()}
        facts['gpus'] = [{'chip': gpu.get('sppci_model'), 'cores': int(gpu['sppci_cores'])
                         if str(gpu.get('sppci_cores', '')).isdigit() else None}
                        for gpu in data.get('SPDisplaysDataType', []) if isinstance(gpu, dict)]
        return facts
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError, TypeError):
        return {'status': 'unavailable'}
