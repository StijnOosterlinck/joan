import glob
import os
import sys
import time

import numpy as np
import pandas as pd
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox, QApplication

from core.joanmoduleaction import JoanModuleAction
from core.statesenum import State
from modules.joanmodules import JOANModules
from .carlainterfacesettings import CarlaInterfaceSettings
from modules.carlainterface.action.agenttypes import AgentTypes
from .carlainterfacesignals import CarlaInterfaceSignals

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


class CarlaInterfaceAction(JoanModuleAction):
    """
    CarlaInterfaceAction is the 'brains' of the module and does most of the calculations and data handling regarding the agents. Inherits
    Agents being the cars/actors you want to control and spawn in the CARLA environment.
    from JoanModuleAction.
    """

    def __init__(self, millis=5):
        """
        Initializes the class
        :param millis: the interval in milliseconds that the module will tick at
        """
        super().__init__(module=JOANModules.CARLA_INTERFACE, millis=millis)

        # Initialize Variables
        self.data = {}
        self.data['ego_agents'] = {}
        self.data['traffic_agents'] = {}
        self.data['connected'] = False
        self.write_news(news=self.data)
        self.time = QtCore.QTime()
        self._data_from_hardware = {}

        self.settings = CarlaInterfaceSettings(module_enum=JOANModules.CARLA_INTERFACE)
        self.settings.before_load_settings.connect(self.prepare_load_settings)
        self.settings.load_settings_done.connect(self.apply_loaded_settings)
        default_settings_file_location = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                      'carlainterface_settings.json')
        if os.path.isfile(default_settings_file_location):
            self.settings.load_from_file(default_settings_file_location)

        self.share_settings(self.settings)

        # CARLA connection variables:
        self.host = 'localhost'
        self.port = 2000
        self._world = None
        self.connected = False
        self._agents = {}
        self.vehicle_tags = []
        self._available_controllers = []

        self.hardware_manager_state_machine = self.singleton_status.get_module_state_machine(
            JOANModules.HARDWARE_MANAGER)
        self.hardware_manager_state_machine.add_state_change_listener(self._hardware_state_change_listener)
        self._hardware_state_change_listener()

        self.sw_controller_state_machine = self.singleton_status.get_module_state_machine(
            JOANModules.STEERING_WHEEL_CONTROL)
        self.sw_controller_state_machine.add_state_change_listener(self._sw_controller_state_change_listener)
        self._sw_controller_state_change_listener()

        # message box for error display
        self.msg = QMessageBox()

        # state handling
        self.state_machine.set_transition_condition(State.INITIALIZED, State.READY, self._init_condition)
        self.state_machine.set_transition_condition(State.READY, State.RUNNING, self._starting_condition)
        self.state_machine.set_transition_condition(State.RUNNING, State.READY, self._stopping_condition)

        # signals
        self._module_signals = CarlaInterfaceSignals(self.module, self)
        self.singleton_signals.add_signals(self.module, self._module_signals)

    def _state_change_listener(self):
        """
        Listens to any state change of the module, whenever the state changes this will be executed.
        :return:
        """
        pass

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
        """ This function is linked to the state change of the hardware manager and updates the state whenever it changes"""
        self.hardware_manager_state = self.singleton_status.get_module_current_state(JOANModules.HARDWARE_MANAGER)

    def _sw_controller_state_change_listener(self):
        """This function is linked to the state change of the sw_controller, if new controllers are initialized they will be
        automatically added to a variable which contains the options in the SW controller combobox"""
        self.sw_controller_state = self.singleton_status.get_module_current_state(JOANModules.STEERING_WHEEL_CONTROL)

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
            if self.connected:
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
            for agent in self._agents:
                self.data['ego_agents'][agent] = self._agents[agent].unpack_vehicle_data()
            self.write_news(news=self.data)
            self._data_from_hardware = self.read_news(JOANModules.HARDWARE_MANAGER)
            try:
                for agent in self._agents:
                    if self._agents[agent].spawned:
                        self._agents[agent].do_while_running(self._data_from_hardware)
            except Exception as inst:
                print('Could not apply control', inst)
        else:
            self.stop()

    def prepare_load_settings(self):
        """
        Prepare the module for new settings: remove all 'old' hardware from the list
        :return:
        """
        # remove_input_device any existing input devices
        for agents in self._agents:
            self.remove_agent(agents)

    def apply_loaded_settings(self):
        """
        Create hardware inputs based on the loaded settings
        :return:
        """
        for ego_vehicle_settings in self.settings.ego_vehicles:
            self.add_agent(AgentTypes.EGOVEHICLE, ego_vehicle_settings)

        for traffic_vehicle_settings in self.settings.traffic_vehicles:
            self.add_agent(AgentTypes.TRAFFICVEHICLE, traffic_vehicle_settings)

    def check_connection(self):
        """
        Checks whether JOAN is connected by returning the connected parameter
        :return:
        """
        return self.connected

    def connect_carla(self):
        """
        This function will try and connect to carla server if it is running in unreal
        If not a message box will pop up and the module will transition to error state.
        """
        if not self.connected:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                self.client = carla.Client(self.host, self.port)  # connecting to server
                self.client.set_timeout(2.0)
                time.sleep(2)
                self._world = self.client.get_world()  # get world object (contains everything)
                blueprint_library = self._world.get_blueprint_library()
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
                self.carla_waypoints = world_map.generate_waypoints(0.5)
                self.data['waypoints'] = self.carla_waypoints
                self.data['map'] = world_map
                print('JOAN connected to CARLA Server!')
                QApplication.restoreOverrideCursor()

                self.connected = True

                # # TODO: untested, settings are only able to be applied after connecting to CARLA
                # self.apply_loaded_settings()

            except RuntimeError as inst:
                QApplication.restoreOverrideCursor()
                self.msg.setText('Could not connect check if CARLA is running in Unreal')
                self.msg.exec()
                self.connected = False
                QApplication.restoreOverrideCursor()

            self.module_dialog.module_widget.btn_connect.setEnabled(not self.connected)
            self.module_dialog.module_widget.btn_disconnect.setEnabled(self.connected)
            self.data['connected'] = self.connected
            self.write_news(news=self.data)

        else:
            self.msg.setText('Already Connected')
            self.msg.exec()

        return self.connected

    def disconnect_carla(self):
        """
        This function will try and disconnect from the carla server, if the module was running it will transition into
        an error state
        """
        if self.connected:
            self.destroy_all()

            self.connected = False
            self.data['connected'] = self.connected
            self.write_news(news=self.data)
            self.vehicle_tags.clear()
            self._spawn_points.clear()

            self.state_machine.request_state_change(State.INITIALIZED, 'Carla Disconnected')

            self.module_dialog.module_widget.btn_connect.setEnabled(not self.connected)
            self.module_dialog.module_widget.btn_disconnect.setEnabled(self.connected)

    def save_opendrive_trajectory(self, world_map):
        """
        Short function to save the currently loaded opendrive file waypoints as a csv file our PD controller can use
        please note that the PSI (heading) for the human compatible reference for FDCA controller is far from ideal
        better to just drive it yourself. PLEASE CHECK THE FILE LOCATION (bottom of this function)
        """
        # TODO: Add dynamic saving of the file in correct path instead of hardcoding the path
        self._waypoints = []
        i = 0
        xvec = np.array([-1, 0])

        waypoints = world_map.generate_waypoints(0.5)
        waypoint = waypoints[0]
        while len(self._waypoints) != len(waypoints):
            angle = waypoint.transform.rotation.yaw
            angle = angle % 360
            angle = (angle + 360) % 360
            if angle > 180:
                angle -= 360

            self._waypoints.append([i, waypoint.transform.location.x, waypoint.transform.location.y, 0, 0, 0, angle, 0])

            temp = waypoint.next(0.2)
            waypoint = temp[0]
            i = i + 1

        print(len(self._waypoints))
        for waypoint in waypoints:
            print(waypoint.lane_width)

        for k in range(0, len(self._waypoints)):

            first_point = np.array([self._waypoints[k][1], self._waypoints[k][2]])
            if k < len(self._waypoints) - 1:
                second_point = np.array([self._waypoints[k + 1][1], self._waypoints[k + 1][2]])
            else:
                second_point = np.array([self._waypoints[0][1], self._waypoints[0][2]])

            dirvec = second_point - first_point
            dirvec_unit = dirvec / np.linalg.norm(dirvec)

            self._waypoints[k][6] = np.math.atan2(dirvec_unit[1], dirvec_unit[0]) - np.math.atan2(xvec[1], xvec[0])

        df = pd.DataFrame(self._waypoints,
                          columns=['Row Name', 'PosX', 'PosY', 'SteeringAngle', 'Throttle', 'Brake', 'Psi', 'Vel'])
        df2 = pd.DataFrame(self._waypoints[0:len(self._waypoints):5],
                           columns=['Row Name', 'PosX', 'PosY', 'SteeringAngle', 'Throttle', 'Brake', 'Psi', 'Vel'])
        df.to_csv(os.path.join(self.module_path, 'action/trajectories', 'opendrive_trajectory.csv'), index=False,
                  header=False)
        df2.to_csv(os.path.join(self.module_path, 'action/trajectories', 'opendrive_trajectory_VISUAL.csv'),
                   index=False,
                   header=True)

    def add_agent(self, agent_type, agent_settings=None):
        number_of_agents = sum([bool(agent_type.__str__() in k) for k in self._agents.keys()]) + 1
        agent_name = agent_type.__str__() + ' ' + str(number_of_agents)

        if not agent_settings:
            agent_settings = agent_type.settings
            if agent_type == AgentTypes.EGOVEHICLE:
                self.settings.ego_vehicles.append(agent_settings)
            if agent_type == AgentTypes.TRAFFICVEHICLE:
                self.settings.traffic_vehicles.append(agent_settings)

            self._agents[agent_name] = agent_type.klass(self, agent_name, agent_settings
                                                        , self.vehicle_tags, self._spawn_points)
            self._agents[agent_name].get_agent_tab.group_agent.setTitle(agent_name)
            self.module_dialog.module_widget.agent_list_layout.addWidget(self._agents[agent_name].get_agent_tab)
            self._agents[agent_name]._open_settings_dialog_from_button()
        else:
            self._agents[agent_name] = agent_type.klass(self, agent_name, agent_settings
                                                        , self.vehicle_tags, self._spawn_points)
            self._agents[agent_name].get_agent_tab.group_agent.setTitle(agent_name)
            self.module_dialog.module_widget.agent_list_layout.addWidget(self._agents[agent_name].get_agent_tab)
            self._agents[agent_name]._open_settings_dialog()

        self._state_change_listener()

        return self._agents[agent_name].get_agent_tab

    def remove_agent(self, agent):
        # remove_input_device controller from the news
        try:
            del self.data[agent.get_agent_list_key]
        except KeyError:  # data is only present if the hardware manager ran since the hardware was added
            pass

        # remove_input_device controller settings
        try:
            self.settings.remove_agent(
                self._agents[agent.get_agent_list_key].settings)
        except ValueError:  # depends if right controller list is present
            pass

        try:
            self.settings.remove_agent(
                self._agents[agent.get_agent_list_key].settings)
        except ValueError:  # depends if right controller list is present
            pass

        # remove dialog
        self._agents[agent.get_agent_list_key].get_agent_tab.setParent(None)

        # delete object
        del self._agents[agent.get_agent_list_key]

        # remove controller from data
        try:
            del self.data[agent]
        except KeyError:  # data is only present if the hardware manager ran since the hardware was added
            pass

        if not self._agents:
            self.stop()

    def initialize(self):
        """
        This function is called before the module is started
        """
        if 'carla' not in sys.modules.keys():
            self.state_machine.request_state_change(State.ERROR,
                                                    "carla module is NOT imported, make sure the API is available and restart the program")

        if self.state_machine.current_state is State.INITIALIZED:
            self.state_machine.request_state_change(State.READY, "You can now add vehicles and start module")
        elif self.state_machine.current_state is State.ERROR and 'carla' in sys.modules.keys():
            self.state_machine.request_state_change(State.INITIALIZED)
        return super().initialize()

    def start(self):
        """
        Starts the module at the millis interval, goes from state ready to running
        :return:
        """
        try:
            self.state_machine.request_state_change(State.RUNNING, "Carla interface Running")
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
            self.state_machine.request_state_change(State.READY, "You can now add vehicles and start the module")

            # for traffic in self.traffic_vehicles:
            #     traffic.stop_traffic()
        except RuntimeError:
            return False
        return super().stop()

    def remove_all(self):
        for agent in list(self._agents):
            self._agents[agent].remove_agent()

    def spawn_all(self):
        """
        Spawn all agents in CARLA
        :return:
        """
        for agent in self._agents:
            if not self._agents[agent].spawned:
                self._agents[agent].spawn()

    def destroy_all(self):
        """
        Destroys all agents currently in simulation
        :return:
        """
        for agent in self._agents:
            self._agents[agent].destroy()
