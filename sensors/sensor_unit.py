
import time
import random
from datetime import datetime
from typing import Dict, Tuple, Optional, Any, List
from threading import Thread



class SensorUnit:

    id : str = ''
    is_active = False

    META_DATA: Dict[str, Any] = {
        'type' : '',
        'brand' : '',
        'last_maintenance_date' :  '',
        'created_at' :  '',
        'is_motion' : False,
        'status' : 'active' #( 'active', 'inactive', 'error', 'maintenance')
    }
    

    SENSORS_ENABLED: Dict[str, bool] = {
        'temperature': False,
        'humidity': False,
        'co2': False, 
        'co': False,
        'smoke': False, 
        'liquefied_petroleum_gas': False, 
        'audio_noise': False, 
        'fine_dust': False, 
        'latitude': False, 
        'longitude': False, 
        'light_detected': False, 
        'timestamp': False,
    }


    SENSOR_RANGES: Dict[str, Tuple[float, float]] = {
        'temperature': (-50, 85),
        'humidity': (0, 100),
        'co2': (0, 5000), 
        'co': (0, 1000),
        'smoke': (0, 1000), 
        'liquefied_petroleum_gas': (0, 1000), 
        'audio_noise': (0, 140), 
        'fine_dust': (0, 999), 
        'latitude': (-90, 90), 
        'longitude': (-180, 180), 
        'light_detected': (True, False), 
        'timestamp': (0, 9999999999),
    }


    OPERATING_RANGES: Dict[str, Tuple[float, float]]= {
        'temperature': (18, 26),
        'humidity': (40, 60),
        'co2': (600, 1200), 
        'co': (0, 35), 
        'smoke': (0, 50),
        'liquefied_petroleum_gas': (0, 30),
        'audio_noise': (45, 75), 
        'fine_dust': (15, 75),
        'latitude': (40.5, 40.9), 
        'longitude': (-74.3, -73.7),
        'timestamp': (0, 9999999999),
    }

    CHANGE_RATIOS: Dict[str, float] = {
        'temperature': 0.01,
        'humidity': 0.02,
        'co2': 0.03,
        'co': 0.05,
        'smoke': 0.08,
        'liquefied_petroleum_gas': 0.05,
        'audio_noise': 0.15, 
        'fine_dust': 0.04, 
        'latitude': 0.001, 
        'longitude': 0.001,
        'light_detected':0.9,
         'timestamp': 1
    }


    def __init__(self, 
                 sensor_id:str, 
                 sensor_metadata: dict = None,
                 sensors_enabled: dict = None, 
                 operating_ranges:dict= None,
                 change_ratios:dict=None, 
                 heartbeat:int = 5, 
                 is_active:bool = True
                 ) -> None:
       
        # sensor id (unique)
        self.id = sensor_id

 

        # set the metadata of the sensor if exist and add new keys if exists
        self.metadata = self.META_DATA.copy()
        if sensor_metadata:
            self.metadata.update(sensor_metadata)

        # sensor variables enabled
        self.sensors_enabled = self.SENSORS_ENABLED.copy()
        if sensors_enabled:
            self.sensors_enabled.update(sensors_enabled)

        # redefine the operating ranges of the sensor if different from default
        self.operating_ranges = self.OPERATING_RANGES.copy()
        if operating_ranges:
            self.operating_ranges.update(operating_ranges)

        # creates a copy from default and updates the changes according instance
        self.change_ratios = self.CHANGE_RATIOS.copy()
        if change_ratios:
            self.change_ratios.update(change_ratios)

        # sensor attributes
        self.heartbeat = heartbeat
        self.data = {}
        self.is_active = False
        self.thread: Optional[Thread] = None
        self.initialize_data()

    


    # read the sensors enabled,
    # create a dictionary with sensor key and empty values
    # iterate through key get the maximum and minim 
    def initialize_data(self) -> None:
        self.data = {}

        # if the sensor is enabled
        for sensor, enabled in self.sensors_enabled.items():
            if enabled and sensor in self.SENSOR_RANGES:
                if sensor in self.operating_ranges:
                    sensor_min, sensor_max = self.operating_ranges[sensor]
                else:
                    sensor_min, sensor_max = self.SENSOR_RANGES[sensor]

                if isinstance(sensor_min, bool):
                    self.data[sensor] = random.choice([True, False])
                else:
                    self.data[sensor] = random.uniform(sensor_min, sensor_max)
            
        self.data['timestamp'] = datetime.now().timestamp()



    def generate_data(self) -> Dict[str, Any]:
        # loop through the self.data dict
        # take the actual value and from it generate a new value
        # save the new value in the dictionary
        # return the dictionary
        for sensor, value in self.data.items():
            if isinstance(value, bool):
                self.data[sensor] = random.choice([True, False])

            if isinstance(value, float):
                min, max = self.operating_ranges[sensor]
                new_value = self.data[sensor] + self.change_ratios[sensor] * random.choice([1, -1])
                if new_value > max:
                    new_value = max
                
                if new_value < min:
                    new_value = min
                
                self.data[sensor] = new_value    
                self.data['timestamp'] = datetime.now().timestamp()

        return self.data
    

    def update_sensors_unit_configuration(self,  
                                          metadata: dict = None,
                                          sensors_enabled: dict = None,
                                          operating_ranges:dict= None,
                                          change_ratios:dict=None, 
                                          heartbeat:int = 5,
                                          is_active:bool = True):
        
        if metadata:
            self.metadata.update(metadata)
        if sensors_enabled:
            self.sensors_enabled.update(sensors_enabled)
        if change_ratios:
            self.change_ratios.update(change_ratios)
        if operating_ranges:
            self.operating_ranges.update(operating_ranges)
        if heartbeat:
            self.heartbeat = heartbeat
        self.is_active = is_active


    def display_info(self) -> None:
        print(f"\n{'='*50}")
        print(f"Sensor information")
        print(f"Sensor id: {self.id}")
        print(f"Metadata: {self.metadata}")
        print(f"Sensors enabled: {self.sensors_enabled}")
        print(f"Sensor operative ranges: {self.operating_ranges}")
        print(f"Change ratios {self.change_ratios}")
        print(f"\n{'='*50}")



    def heartbeat_loop(self) -> None:
        while self.is_active:
            self.generate_data()
            print(f"[{self.id} {self.data}]")
            time.sleep(self.heartbeat) 


    def start(self) -> None:
        if self.is_active:
            print(f"The device is active and the status is {self.metadata['status']}" )
            return
        
        self.is_active = True
        self.thread = Thread(target=self.heartbeat_loop, daemon=True)
        self.thread.start()

    
    def stop(self) -> None:
        self.is_active = False


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

                
                




