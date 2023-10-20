import copy
import math
import os
import random
from enum import Enum

import carla
import numpy as np
from PyQt5 import QtCore
from PyQt5 import uic, QtWidgets
from PyQt5.QtWidgets import QMessageBox

from modules.carlainterface.carlainterface_agenttypes import AgentTypes
from modules.joanmodules import JOANModules


class NPCVehicleSettingsDialog(QtWidgets.QDialog):
    def __init__(self, settings, module_manager, parent=None):
        super().__init__(parent)

        self.settings = settings
        self.module_manager = module_manager
        self.carla_interface_overall_settings = self.module_manager.module_settings
        uic.loadUi(os.path.join(os.path.dirname(os.path.realpath(__file__)), "ui/npc_vehicle_settings_ui.ui"), self)
        self.msg_box = QMessageBox()
        self.msg_box.setTextFormat(QtCore.Qt.RichText)

        self.button_box_vehicle_settings.button(self.button_box_vehicle_settings.RestoreDefaults).clicked.connect(
            self._set_default_values)
        self.btn_apply_parameters.clicked.connect(self.update_parameters)
        self.btn_update.clicked.connect(lambda: self.update_settings(self.settings))
        self.customSpawnpointCheckBox.stateChanged.connect(self.update_spinbox_enabled)
        self.display_values()

        self.update_settings(self.settings)

    def show(self):
        self.update_settings(self.settings)
        super().show()

    def update_spinbox_enabled(self):
        for spinbox in [self.spawnpointXSpinBox, self.spawnpointYSpinBox, self.spawnpointZSpinBox, self.spawnpointYawSpinBox]:
            spinbox.setEnabled(self.customSpawnpointCheckBox.isChecked())

    def update_parameters(self):
        self.settings.selected_npc_controller = self.combo_controller.currentText()
        self.settings.selected_car = self.combo_car_type.currentText()
        self.settings.selected_spawnpoint = self.combo_spawnpoints.currentText()

        self.settings.use_custom_spawn_point = self.customSpawnpointCheckBox.isChecked()
        self.settings.custom_spawn_point_location[0] = self.spawnpointXSpinBox.value()
        self.settings.custom_spawn_point_location[1] = self.spawnpointYSpinBox.value()
        self.settings.custom_spawn_point_location[2] = self.spawnpointZSpinBox.value()
        self.settings.custom_spawn_point_rotation = self.spawnpointYawSpinBox.value()

        for settings in self.carla_interface_overall_settings.agents.values():
            if settings.identifier != self.settings.identifier:  # exlude own settings
                if settings.selected_spawnpoint == self.combo_spawnpoints.currentText() and settings.selected_spawnpoint != 'None':
                    self.msg_box.setText('This spawnpoint was already chosen for another agent \n'
                                         'resetting spawnpoint to None')
                    self.msg_box.exec()
                    self.settings.selected_spawnpoint = 'None'
                    break
                else:
                    self.settings.selected_spawnpoint = self.combo_spawnpoints.currentText()

        self.display_values()

    def accept(self):
        self.update_parameters()
        super().accept()

    def display_values(self, settings_to_display=None):
        if not settings_to_display:
            settings_to_display = self.settings

        self.customSpawnpointCheckBox.setChecked(settings_to_display.use_custom_spawn_point)
        self.spawnpointXSpinBox.setValue(settings_to_display.custom_spawn_point_location[0])
        self.spawnpointYSpinBox.setValue(settings_to_display.custom_spawn_point_location[1])
        self.spawnpointZSpinBox.setValue(settings_to_display.custom_spawn_point_location[2])
        self.spawnpointYawSpinBox.setValue(settings_to_display.custom_spawn_point_rotation)

        idx_controller = self.combo_controller.findText(settings_to_display.selected_npc_controller)
        self.combo_controller.setCurrentIndex(idx_controller)

        idx_car = self.combo_car_type.findText(settings_to_display.selected_car)
        self.combo_car_type.setCurrentIndex(idx_car)

        self.combo_spawnpoints.setCurrentText(settings_to_display.selected_spawnpoint)
        self.update_spinbox_enabled()

    def _set_default_values(self):
        self.display_values(AgentTypes.NPC_VEHICLE.settings())

    def update_settings(self, settings):
        # update available vehicles
        self.combo_car_type.clear()
        self.combo_car_type.addItem('None')
        self.combo_car_type.addItems(self.module_manager.vehicle_tags)
        idx = self.combo_car_type.findText(settings.selected_car)
        if idx != -1:
            self.combo_car_type.setCurrentIndex(idx)

        # update available spawn_points:
        self.combo_spawnpoints.clear()
        self.combo_spawnpoints.addItem('None')
        self.combo_spawnpoints.addItems(self.module_manager.spawn_points)
        idx = self.combo_spawnpoints.findText(
            settings.selected_spawnpoint)
        if idx != -1:
            self.combo_spawnpoints.setCurrentIndex(idx)

        # update available controllers according to current settings:
        self.combo_controller.clear()
        self.combo_controller.addItem('None')
        npc_controller_manager_settings = self.module_manager.central_settings.get_settings(JOANModules.NPC_CONTROLLER_MANAGER)
        for controller_identifier, controller_settings in npc_controller_manager_settings.controllers.items():
            self.combo_controller.addItem(controller_identifier)
        idx = self.combo_controller.findText(settings.selected_npc_controller)
        if idx != -1:
            self.combo_controller.setCurrentIndex(idx)


class NPCVehicleProcess:
    def __init__(self, carla_mp, settings, shared_variables):
        self.settings = settings
        self.shared_variables = shared_variables
        self.carlainterface_mp = carla_mp
        self.npc_controller_shared_variables = carla_mp.npc_controller_shared_variables

        if self.settings.selected_car != 'None':
            self._BP = random.choice(self.carlainterface_mp.vehicle_blueprint_library.filter("vehicle." + self.settings.selected_car))
        self._control = carla.VehicleControl()
        self._rear_axle_in_vehicle_frame = np.array([0., 0., 0.])
        self.world_map = self.carlainterface_mp.world.get_map()
        torque_curve = []
        gears = []

        torque_curve.append(carla.Vector2D(x=10., y=600.))
        torque_curve.append(carla.Vector2D(x=14000., y=600.))
        gears.append(carla.GearPhysicsControl(ratio=5., down_ratio=0.0, up_ratio=100.))

        if self.settings.selected_spawnpoint != 'None' or self.settings.use_custom_spawn_point:
            if self.settings.selected_car != 'None':
                if self.settings.use_custom_spawn_point:
                    spawn_transform = carla.Transform(location=carla.Location(*self.settings.custom_spawn_point_location),
                                                      rotation=carla.Rotation(yaw=self.settings.custom_spawn_point_rotation))
                else:
                    spawn_transform = self.carlainterface_mp.spawn_point_objects[self.carlainterface_mp.spawn_points.index(self.settings.selected_spawnpoint)]
                self.spawned_vehicle = self.carlainterface_mp.world.spawn_actor(self._BP, spawn_transform)
                physics = self.spawned_vehicle.get_physics_control()
                physics.torque_curve = torque_curve
                physics.max_rpm = 14000
                physics.moi = 1.5
                physics.damping_rate_full_throttle = 0.35
                physics.damping_rate_zero_throttle_clutch_engaged = 0.35  # simulate that the clutch is always disengaged with no throttle
                physics.damping_rate_zero_throttle_clutch_disengaged = 0.35
                physics.clutch_strength = 1000  # very big no clutch
                physics.final_ratio = 1  # ratio from transmission to wheels
                physics.forward_gears = gears
                physics.mass = 1475  # kg (Audi S3)
                physics.drag_coefficient = 0.24
                physics.gear_switch_time = 0.0
                physics.use_gear_autobox = False

                wheels = copy.copy(physics.wheels)
                wheels[0].max_brake_torque = 1500.
                wheels[1].max_brake_torque = 1500.
                wheels[2].max_brake_torque = 1400.
                wheels[3].max_brake_torque = 1400.
                physics.wheels = wheels

                self.spawned_vehicle.apply_physics_control(physics)
                self.shared_variables.max_steering_angle = np.radians(wheels[0].max_steer_angle)

                rotation = self.spawned_vehicle.get_transform().rotation
                rotation_matrix = self.get_rotation_matrix_from_carla(rotation.roll, rotation.pitch, rotation.yaw)

                rear_axle_in_world_frame = (((wheels[3].position - wheels[2].position) / 2) + wheels[2].position) / 100.
                position_difference = rear_axle_in_world_frame - self.spawned_vehicle.get_transform().location
                position_difference = np.array([position_difference.x, position_difference.y, position_difference.z])

                self._rear_axle_in_vehicle_frame = np.linalg.inv(rotation_matrix) @ position_difference

    def do(self):
        if self.settings.selected_npc_controller != 'None' and hasattr(self, 'spawned_vehicle'):
            self._control.steer = self.npc_controller_shared_variables.controllers[self.settings.selected_npc_controller].steering_angle / math.radians(450)
            self._control.reverse = self.npc_controller_shared_variables.controllers[self.settings.selected_npc_controller].reverse
            self._control.hand_brake = self.npc_controller_shared_variables.controllers[self.settings.selected_npc_controller].handbrake
            self._control.brake = self.npc_controller_shared_variables.controllers[self.settings.selected_npc_controller].brake
            self._control.throttle = self.npc_controller_shared_variables.controllers[self.settings.selected_npc_controller].throttle

            self.spawned_vehicle.apply_control(self._control)

        self.set_shared_variables()

    def destroy(self):
        if hasattr(self, 'spawned_vehicle') and self.spawned_vehicle.is_alive:
            self.spawned_vehicle.destroy()

    def set_shared_variables(self):
        if hasattr(self, 'spawned_vehicle'):
            actor_snap_shot = self.carlainterface_mp.world.get_snapshot().find(self.spawned_vehicle.id)

            rotation = actor_snap_shot.get_transform().rotation
            center_location = actor_snap_shot.get_transform().location
            self.shared_variables.transform = [center_location.x,
                                               center_location.y,
                                               center_location.z,
                                               rotation.yaw,
                                               rotation.pitch,
                                               rotation.roll]
            linear_velocity = actor_snap_shot.get_velocity()
            self.shared_variables.velocities_in_world_frame = [linear_velocity.x,
                                                               linear_velocity.y,
                                                               linear_velocity.z,
                                                               actor_snap_shot.get_angular_velocity().x,
                                                               actor_snap_shot.get_angular_velocity().y,
                                                               actor_snap_shot.get_angular_velocity().z]

            rotation_matrix = self.get_rotation_matrix_from_carla(rotation.roll, rotation.pitch, rotation.yaw)
            velocities_in_vehicle_frame = np.linalg.inv(rotation_matrix) @ np.array([linear_velocity.x, linear_velocity.y, linear_velocity.z])
            self.shared_variables.velocities_in_vehicle_frame = velocities_in_vehicle_frame

            center_location_as_np = np.array([center_location.x, center_location.y, center_location.z])
            self.shared_variables.rear_axle_position = center_location_as_np + rotation_matrix @ self._rear_axle_in_vehicle_frame

            self.shared_variables.accelerations_in_world_frame = [actor_snap_shot.get_acceleration().x,
                                                                  actor_snap_shot.get_acceleration().y,
                                                                  actor_snap_shot.get_acceleration().z]

            accelerations = actor_snap_shot.get_acceleration()
            self.shared_variables.accelerations_in_world_frame = [accelerations.x,
                                                                  accelerations.y,
                                                                  accelerations.z]

            accelerations_in_vehicle_frame = np.linalg.inv(rotation_matrix) @ np.array([accelerations.x, accelerations.y, accelerations.z])
            self.shared_variables.accelerations_in_vehicle_frame = accelerations_in_vehicle_frame

            latest_applied_control = self.spawned_vehicle.get_control()
            self.shared_variables.applied_input = [float(latest_applied_control.steer),
                                                   float(latest_applied_control.reverse),
                                                   float(latest_applied_control.hand_brake),
                                                   float(latest_applied_control.brake),
                                                   float(latest_applied_control.throttle)]

    @staticmethod
    def get_rotation_matrix_from_carla(roll, pitch, yaw, degrees=True):
        """ calculation based on this github issue: https://github.com/carla-simulator/carla/issues/58 because carla uses some rather unconventional conventions."""
        if degrees:
            roll, pitch, yaw = np.radians([roll, pitch, yaw])

        yaw_matrix = np.array([
            [math.cos(yaw), -math.sin(yaw), 0],
            [math.sin(yaw), math.cos(yaw), 0],
            [0, 0, 1]
        ])

        pitch_matrix = np.array([
            [math.cos(pitch), 0, -math.sin(pitch)],
            [0, 1, 0],
            [math.sin(pitch), 0, math.cos(pitch)]
        ])

        roll_matrix = np.array([
            [1, 0, 0],
            [0, math.cos(roll), math.sin(roll)],
            [0, -math.sin(roll), math.cos(roll)]
        ])

        rotation_matrix = yaw_matrix @ pitch_matrix @ roll_matrix
        return rotation_matrix


class NPCVehicleSettings:
    """
    Class containing the default settings for an egovehicle
    """

    def __init__(self, identifier=''):
        """
        Initializes the class with default variables
        """
        self.selected_npc_controller = 'None'
        self.selected_spawnpoint = 'Spawnpoint 0'
        self.use_custom_spawn_point = False
        self.custom_spawn_point_location = [0.0, 0.0, 0.0]
        self.custom_spawn_point_rotation = 0.0

        self.selected_car = 'hapticslab.audi'
        self.identifier = identifier

        self.agent_type = AgentTypes.NPC_VEHICLE

    def as_dict(self):
        return_dict = copy.copy(self.__dict__)
        for key, item in self.__dict__.items():
            if isinstance(item, Enum):
                return_dict[key] = item.value

        return return_dict

    def set_from_loaded_dict(self, loaded_dict):
        for key, value in loaded_dict.items():
            if key == 'agent_type':
                self.__setattr__(key, AgentTypes(value))
            else:
                self.__setattr__(key, value)

    def __str__(self):
        return self.identifier
