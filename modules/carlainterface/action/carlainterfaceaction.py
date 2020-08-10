from PyQt5 import QtCore, uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox, QApplication

from .agents.egovehicle import Egovehicle
from .agents.trafficvehicle import Trafficvehicle
from .carlainterfacesettings import  CarlainterfaceSettings, EgoVehicleSettings, TrafficVehicleSettings


from modules.joanmodules import JOANModules
from process.joanmoduleaction import JoanModuleAction
from process.statesenum import State
from process.status import Status


import time
import random
import os
import sys
import glob
import pandas as pd
import numpy as np
import math

msg_box = QMessageBox()
msg_box.setTextFormat(QtCore.Qt.RichText)

try:
    sys.path.append(glob.glob('carla_pythonapi/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
    import carla  

except IndexError:
    msg_box.setText("""
                <h3> Could not find the carla python API! </h3>
                <h3> Check whether you copied the egg file correctly, reference:
            <a href=\"https://joan.readthedocs.io/en/latest/setup-run-joan/#getting-necessary-python3-libraries-to-run-joan\">https://joan.readthedocs.io/en/latest/setup-run-joan/#getting-necessary-python3-libraries-to-run-joan</a>
            </h3>
            """)
    msg_box.exec()
    pass

class CarlainterfaceAction(JoanModuleAction):
    """
    CarlainterfaceAction is the 'brains' of the module and does most of the calculations and data handling regarding the agents. Inherits
    Agents being the cars/actors you want to control and spawn in the CARLA environment.
    from JoanModuleAction.
    """
    def __init__(self, millis=5):
        """
        Initializes the class
        :param millis: the interval in milliseconds that the module will tick at
        """
        super().__init__(module=JOANModules.CARLA_INTERFACE, millis=millis)

        #Initialize Variables
        self.data = {}
        self.data['ego_agents'] = {}
        self.data['traffic_agents'] = {}
        self.data['connected'] = False
        self.write_news(news=self.data)
        self.time = QtCore.QTime()
        self._data_from_hardware = {}

        self.settings = CarlainterfaceSettings(module_enum=JOANModules.CARLA_INTERFACE)

        #Carla connection variables:
        self.host = 'localhost'
        self.port = 2000
        self.connected = False
        self.vehicle_tags = []
        self.vehicles = []
        self.traffic_vehicles = []

        #initialize modulewide state handler
        self.status = Status()

        self._available_controllers = []

        self.hardware_manager_state_machine = self.status.get_module_state_machine(JOANModules.HARDWARE_MANAGER)
        self.hardware_manager_state_machine.add_state_change_listener(self._hardware_state_change_listener)
        self._hardware_state_change_listener()

        self.sw_controller_state_machine = self.status.get_module_state_machine(JOANModules.STEERING_WHEEL_CONTROL)
        self.sw_controller_state_machine.add_state_change_listener(self._sw_controller_state_change_listener)
        self._sw_controller_state_change_listener()

        #message box for error display
        self.msg = QMessageBox()

        ## State handling (these are for now all the same however maybe in the future you want to add other functionality)
        self.state_machine.set_transition_condition(State.IDLE, State.READY, self._init_condition)
        self.state_machine.set_transition_condition(State.READY, State.RUNNING, self._starting_condition)
        self.state_machine.set_transition_condition(State.RUNNING, State.READY, self._stopping_condition)

        default_settings_file_location = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                      'agent_manager_settings.json')
        if os.path.isfile(default_settings_file_location):
            self.settings.load_from_file(default_settings_file_location)

        self.share_settings(self.settings)

    @property 
    def vehicle_bp_library(self):
        return self._vehicle_bp_library

    @property 
    def world(self):
        return self._world
    
    @property 
    def spawnpoints(self):
        return self._spawn_points

    def _hardware_state_change_listener(self):
        " This function is linked to the state change of the hardware manager and updates the state whenever it changes"

        self.hardware_manager_state = self.status.get_module_current_state(JOANModules.HARDWARE_MANAGER)

    def _sw_controller_state_change_listener(self):
        """This function is linked to the state change of the sw_controller, if new controllers are initialized they will be
        automatically added to a variable which contains the options in the SW controller combobox"""
        self.sw_controller_state = self.status.get_module_current_state(JOANModules.STEERING_WHEEL_CONTROL)

    def _starting_condition(self):
        """
        Conditions is that JOAN should be connected to CARLA else it wont start
        :return:
        """
        try:
            if self.connected is True:

                return True, ''
            else:
                return False, 'Carla is not connected!'
        except KeyError:
            return False, 'Could not check whether carla is connected'


    def _init_condition(self):
        try:
            if self.connected is True:
                # TODO: move this example to the new enum
                return True, ''
            else:
                return False, 'Carla is not connected'
        except KeyError:
            return False, 'Could not check whether carla is connected'

    def _stopping_condition(self):
        try:
            if self.connected is True:
                # TODO: move this example to the new enum
                return True, ''
            else:
                return False, 'Carla is not connected'
        except KeyError:
            return False, 'Could not check whether carla is connected'

    def do(self):
        """
        This function is called every controller tick of this module implement your main calculations here
        """
        if self.connected:
            for agent in self.vehicles:
                self.data['ego_agents'][agent.vehicle_nr] = agent.unpack_vehicle_data()
            self.write_news(news=self.data)
            self._data_from_hardware = self.read_news(JOANModules.HARDWARE_MANAGER)
            try:
                for items in self.vehicles:
                    if items.spawned:
                        items.apply_control(self._data_from_hardware)
                for items in self.traffic_vehicles:
                    if items.spawned:
                        items.process()
            except Exception as inst:
                print('Could not apply control', inst)
        else:
            self.stop()



    def check_connection(self):
        """
        Checks whether JOAN is connected by returning the connected parameter
        :return:
        """
        return self.connected

    def connect(self):
        """
        This function will try and connect to carla server if it is running in unreal
        If not a message box will pop up and the module will transition to error state.
        """
        if not self.connected:
            try:
                print(' connecting')
                QApplication.setOverrideCursor(Qt.WaitCursor)
                self.client = carla.Client(self.host, self.port)  # connecting to server
                self.client.set_timeout(2.0)
                time.sleep(2)
                self._world = self.client.get_world()  # get world object (contains everything)
                blueprint_library = self.world.get_blueprint_library()
                self._vehicle_bp_library = blueprint_library.filter('vehicle.*')
                for items in self.vehicle_bp_library:
                    self.vehicle_tags.append(items.id[8:])
                world_map = self._world.get_map()
                self._spawn_points = world_map.get_spawn_points()
                self.nr_spawn_points = len(self._spawn_points)

                ## Uncomment this if you want to save the opendrive trajectory to a csv file,
                ## PLEASE CHECK THE FILE SAVING LOCATION!!

                # print('saving current opendrive trajectory to csv file')
                # self.save_opendrive_trajectory(world_map)

                print('JOAN connected to CARLA Server!')
                QApplication.restoreOverrideCursor()

                self.connected = True
            except RuntimeError as inst:
                QApplication.restoreOverrideCursor()
                self.msg.setText('Could not connect check if CARLA is running in Unreal')
                self.msg.exec()
                self.connected = False
                QApplication.restoreOverrideCursor()

            self.data['connected'] = self.connected
            self.write_news(news=self.data)

        else:
            self.msg.setText('Already Connected')
            self.msg.exec()

        return self.connected

    def disconnect(self):
        """
        This function will try and disconnect from the carla server, if the module was running it will transition into
        an error state
        """
        if self.connected:
            print('Disconnecting')
            for cars in self.vehicles:
                cars.destroy_car()

            self.client = None
            self._world = None
            self.connected = False
            self.data['connected'] = self.connected
            self.write_news(news=self.data)

            self.state_machine.request_state_change(State.IDLE, 'Carla Disconnected')

        return self.connected

    def save_opendrive_trajectory(self, world_map):
        """
        Short function to save the currently loaded opendrive file waypoints as a csv file our PD controller can use
        please note that the PSI (heading) for the human compatible reference for FDCA controller is far from ideal
        better to just drive it yourself. PLEASE CHECK THE FILE LOCATION (bottom of this function)
        """
        #TODO: Add dynamic saving of the file in correct path instead of hardcoding the path
        self._waypoints = []
        i = 0
        xvec = np.array([-1, 0])

        waypoints = world_map.generate_waypoints(0.2)
        waypoint = waypoints[0]
        while len(self._waypoints) != len(waypoints):
            angle = waypoint.transform.rotation.yaw
            angle = angle % 360
            angle = (angle + 360) % 360
            if (angle > 180):
                angle -= 360

            self._waypoints.append([i, waypoint.transform.location.x, waypoint.transform.location.y, 0 , 0 , 0 , angle, 0])

            temp = waypoint.next(0.2)
            waypoint = temp[0]
            i = i + 1

        for k in range(0, len(self._waypoints)):
            FirstPoint = np.array([self._waypoints[k][1], self._waypoints[k][2]])
            if k < len(self._waypoints)-1:
                SecondPoint = np.array([self._waypoints[k+1][1], self._waypoints[k+1][2]])
            else:
                SecondPoint =  np.array([self._waypoints[0][1], self._waypoints[0][2]])

            dirvec = SecondPoint - FirstPoint
            dirvec_unit = dirvec/np.linalg.norm(dirvec)

            self._waypoints[k][6] = np.math.atan2(dirvec_unit[1], dirvec_unit[0]) - np.math.atan2(xvec[1], xvec[0])


        self._waypoints_visual = self._waypoints[0:len(self._waypoints):5]

        df = pd.DataFrame(self._waypoints, columns=['Row Name','PosX', 'PosY','SteeringAngle', 'Throttle', 'Brake', 'Psi', 'Vel'])
        df2 = pd.DataFrame(self._waypoints_visual, columns=['Row Name','PosX','PosY','SteeringAngle','Throttle','Brake','Psi','Vel'])
        df.to_csv(r'C:\Repositories\joan\modules\steeringwheelcontrol\action\swcontrollers\trajectories\opendrive_trajectory.csv', index=False, header=False)
        df2.to_csv(r'C:\Repositories\joan\modules\steeringwheelcontrol\action\swcontrollers\trajectories\opendrive_trajectory_VISUAL.csv', index=False, header=True)

    def add_ego_agent(self, ego_vehicle_settings =None):
        """
        Adds an 'Ego Agent', or a vehicle that a user can control by selecting an input.
        :param ego_vehicle_settings:
        :return:
        """
        is_a_new_ego_agent = not ego_vehicle_settings

        if is_a_new_ego_agent:
            ego_vehicle_settings = EgoVehicleSettings()
            self.settings.ego_vehicles.append(ego_vehicle_settings)

        self.vehicles.append(Egovehicle(self, len(self.vehicles), self.nr_spawn_points, self.vehicle_tags, ego_vehicle_settings))

        " only make controller available for first car for now"
        for vehicle in self.vehicles[1:]:
            vehicle.settings_dialog.combo_sw_controller.setEnabled(False)

        return self.vehicles

    def add_traffic_agent(self, traffic_vehicle_settings = None):
        """
        Adds a traffic agent which can be controlled by PD control (throttle and steering)
        :param traffic_vehicle_settings:
        :return:
        """
        is_a_new_traffic_agent = not traffic_vehicle_settings

        if is_a_new_traffic_agent:
            traffic_vehicle_settings = TrafficVehicleSettings()
            self.settings.traffic_vehicles.append(traffic_vehicle_settings)

        self.traffic_vehicles.append(Trafficvehicle(self, len(self.traffic_vehicles), self.nr_spawn_points, self.vehicle_tags, traffic_vehicle_settings))

        return self.traffic_vehicles

    def initialize(self):
        """
        This function is called before the module is started
        """
        if 'carla' not in sys.modules.keys():
            self.state_machine.request_state_change(State.ERROR, "carla module is NOT imported, make sure the API is available and restart the program")

        if self.state_machine.current_state is State.IDLE:

            self.connect()
            self.state_machine.request_state_change(State.READY, "You can now add vehicles and start module")
        elif self.state_machine.current_state is State.ERROR and 'carla' in sys.modules.keys():
           self.state_machine.request_state_change(State.IDLE)
        return super().initialize()

    def start(self):
        """
        Starts the module at the millis interval, goes from state ready to running
        :return:
        """
        try:
            self.state_machine.request_state_change(State.RUNNING,"Carla interface Running")
            self.time.restart()
            return super().start()

        except RuntimeError:
            return False


    def stop(self):
        """
        Stops the module from running and will go from state running to ready
        :return:
        """
        try:
            # for vehicle in self.vehicles:
                # vehicle.get_available_inputs()
                # vehicle.get_available_controllers()
            self.state_machine.request_state_change(State.READY, "You can now add vehicles and start the module")

            for traffic in self.traffic_vehicles:
                traffic.stop_traffic()
        except RuntimeError:
            return False
        return super().stop()

    def load_settings_from_file(self, settings_file_to_load):
        """
        Loads appropriate settings from .json file
        :param settings_file_to_load:
        :return:
        """
        self.settings.load_from_file(settings_file_to_load)
        self.share_settings(self.settings)

    def save_settings_to_file(self, file_to_save_in):
        """
        Saves current settings to json file
        :param file_to_save_in:
        :return:
        """
        self.settings.save_to_file(file_to_save_in)