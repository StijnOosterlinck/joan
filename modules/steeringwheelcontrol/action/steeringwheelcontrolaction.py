from PyQt5 import QtCore

import numpy as np

from modules.joanmodules import JOANModules
from process.joanmoduleaction import JoanModuleAction
from .swcontrollertypes import SWControllerTypes
from process import Status
from process.statesenum import State
from .steeringwheelcontrolsettings import SteeringWheelControlSettings, PDcontrollerSettings

from .swcontrollers.manualswcontroller import ManualSWController


class SteeringWheelControlAction(JoanModuleAction):

    def __init__(self, millis=10):
        super().__init__(module=JOANModules.STEERING_WHEEL_CONTROL, millis=millis)

        # initialize modulewide state handler
        self.status = Status()

        self.settings = SteeringWheelControlSettings(module_enum=JOANModules.STEERING_WHEEL_CONTROL)

        self._controllers = {}
        # self.add_controller(controller_type=SWControllerTypes.MANUAL)
        # self.add_controller(controller_type=SWControllerTypes.PD_SWCONTROLLER)
        # self.add_controller(controller_type=SWControllerTypes.FDCA_SWCONTROLLER)

        self._current_controller = None
        #self.set_current_controller(SWControllerTypes.MANUAL)

        #Setup state machine transition conditions
        self.state_machine.set_transition_condition(State.IDLE, State.READY, self._init_condition)
        self.state_machine.set_transition_condition(State.READY, State.RUNNING, self._starting_condition)
        self.state_machine.set_transition_condition(State.RUNNING, State.READY, self._stopping_condition)

        # set up news
        self.data = {}
        self.data['sw_torque'] = 0
        self.data['lat_error'] = 0
        self.data['heading_error'] = 0
        self.data['lat_error_rate'] = 0
        self.data['heading_error_rate'] = 0
        self.write_news(news=self.data)

        self.share_settings(self.settings)

    def update_vehicle_list(self):
        carla_data = self.read_news(JOANModules.CARLA_INTERFACE)
        vehicle_list = carla_data['vehicles']
        return vehicle_list

    def _starting_condition(self):
        try:
            return True, ''
        except KeyError:
            return False, 'Could not check whether carla is connected'


    def _init_condition(self):
        try:
            return True
        except KeyError:
            return False, 'Could not check whether carla is connected'

    def _stopping_condition(self):
        try:
            return True
        except KeyError:
            return False, 'Could not check whether carla is connected'

    def do(self):
        """
        This function is called every controller tick of this module implement your main calculations here
        """

        sim_data_in = self.read_news(JOANModules.CARLA_INTERFACE)
        hw_data_in = self.read_news(JOANModules.HARDWARE_MANAGER)

        if self.current_controller is not None:
            data_out = self._current_controller.do(sim_data_in, hw_data_in)
            self.data['sw_torque'] = data_out['sw_torque']


        self.write_news(news=self.data)

    def initialize(self):
        """
        This function is called before the module is started
        """
        try:
            if self.state_machine.current_state == State.IDLE:
                self.state_machine.request_state_change(State.READY, 'You can now start the Module')
            elif self.state_machine.current_state == State.ERROR:
                self.state_machine.request_state_change(State.IDLE)

        except RuntimeError:
            return False
        return super().initialize()

    def add_controller(self, controller_type):
        #add appropriate settings
        if controller_type == SWControllerTypes.PD_SWCONTROLLER:
            self.settings.pd_controllers.append(controller_type.settings)
        if controller_type == SWControllerTypes.FDCA_SWCONTROLLER:
            self.settings.fdca_controllers.append(controller_type.settings)
        if controller_type == SWControllerTypes.MANUAL:
            self.settings.manual_controllers.append(controller_type.settings)


        number_of_controllers = sum([bool(controller_type.__str__() in k) for k in self._controllers.keys()]) + 1
        controller_list_key = controller_type.__str__() + ' ' + str(number_of_controllers)
        self._controllers[controller_list_key] = controller_type.klass(self, controller_list_key, controller_type.settings)
        self._controllers[controller_list_key].get_controller_tab.controller_groupbox.setTitle(controller_list_key)
        return self._controllers[controller_list_key].get_controller_tab

    def remove_controller(self, controller):
        self._controllers[controller.get_controller_list_key].get_controller_tab.setParent(None)
        del self._controllers[controller.get_controller_list_key]

        try:
            del self.data[controller]
        except KeyError:  # data is only present if the hardware manager ran since the hardware was added
            pass

        if not self._controllers:
            self.stop()





    def set_current_controller(self, controller_type: SWControllerTypes):
        self._current_controller = self._controllers[controller_type]
        current_state = self.state_machine.current_state
        # current_state = self.module_state_handler.get_current_state()

        # if current_state is not State.RUNNING:
        #     self.state_machine.request_state_change(State.READY)

    def start(self):
        try:
            self.state_machine.request_state_change(State.RUNNING, 'Module Running')
            print('start')
        except RuntimeError:
            return False
        return super().start()

    def stop(self):
        try:
            self.state_machine.request_state_change(State.READY, 'Module Running')
            print('stop')
        except RuntimeError:
            return False
        return super().stop()

    @property
    def controllers(self):
        return self._controllers

    @property
    def current_controller(self):
        return self._current_controller
