
from sensors import SensorUnit
import time
import random
from datetime import datetime
from typing import Dict, Tuple, Optional, Any, List
from threading import Thread


if __name__ == '__main__':


    config1: Dict[str, bool] = {
        'temperature': True,
        'humidity': True,
        'co2': True
    }

    config2: Dict[str, bool] = {
        'temperature': True,
        'humidity': True,
        'co2': True, 
        'co': True,
        'smoke': True, 
        'liquefied_petroleum_gas': True, 
        'audio_noise': True, 
        'fine_dust': True, 
        'latitude': True, 
        'longitude': True, 
        'light_detected': True, 
    }

    config3: Dict[str, bool] = {
        'temperature': False,
        'humidity': False,
        'co2': False, 
        'co': False,
        'smoke': False, 
        'liquefied_petroleum_gas': False, 
        'audio_noise': False, 
        'fine_dust': False, 
        'latitude': True, 
        'longitude': True, 
        'light_detected': True, 
    }

    sensorUnit_1 = SensorUnit(
        sensor_id='Sensor 1',
        sensors_enabled = config1,
        is_active =True,
        heartbeat=2
    )

    sensorUnit_1.display_info()
    sensorUnit_1.start()
    time.sleep(2)
    sensorUnit_1.start()
    time.sleep(10)
    sensorUnit_1.update_sensors_unit_configuration(sensors_enabled=config2, heartbeat=2)
    sensorUnit_1.initialize_data()
    time.sleep(5)
    sensorUnit_1.update_sensors_unit_configuration(sensors_enabled=config3, heartbeat=1)
    sensorUnit_1.initialize_data()
    time.sleep(10)
    sensorUnit_1.stop()

                