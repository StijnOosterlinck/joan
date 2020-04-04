from process import Control, State, translate
from PyQt5 import QtCore
from modules.hardwarecommunication.action.states import HardwarecommunicationStates
from modules.hardwarecommunication.action.hardwarecommunication import *
import os

class HardwarecommunicationWidget(Control):
    def __init__(self, *args, **kwargs):
        kwargs['millis'] = 'millis' in kwargs.keys() and kwargs['millis'] or 5
        kwargs['callback'] = [self.do]  # method will run each given millis
        Control.__init__(self, *args, **kwargs)
        
        self.createWidget(ui=os.path.join(os.path.dirname(os.path.realpath(__file__)),"hardwarecommunication.ui"))
        self.Inputdata = {}

        # creating a self.moduleStateHandler which also has the moduleStates in self.moduleStateHandler.states
        self.defineModuleStateHandler(module=self, moduleStates=HardwarecommunicationStates())
        self.moduleStateHandler.stateChanged.connect(self.handlemodulestate)
        self.masterStateHandler.stateChanged.connect(self.handlemasterstate)
        
        # use Action with state handling, using only this widgets state changes
        try:
            self.action = HardwarecommunicationAction()
        except Exception as inst:
            print(inst)


        self._input = BaseInput(self)
 
        self.Inputs = dict([("Keyboard",Keyboard(self)),("Mouse",Mouse(self)),("Joystick",Joystick(self))])

        #initialize input with none (not catching any inputs)
        #self.Inputdata = self._input.process
        self.writeNews(channel=self, news=self.Inputdata)


    # callback class is called each time a pulse has come from the Pulsar class instance
    def do(self):
        try:
            self.Inputdata = self._input.process()
            self.writeNews(channel=self, news=self.Inputdata)
        except Exception as e:
            print(e)

    @QtCore.pyqtSlot(str)
    def _setmillis(self, millis):
        try:
            millis = int(millis)
            self.setInterval(millis)
        except:
            pass

    def _show(self):
        self.window.show()
        moduleStatesDict = self.moduleStates.getStates()
        for state in moduleStatesDict:
            print('in HardwarecommunicationStates bij show', state, moduleStatesDict[state])


    def start(self):
        if not self.window.isVisible():
            self._show()
        self.moduleStateHandler.requestStateChange(self.moduleStates.HARDWARECOMMUNICATION.RUNNING)
        self.startPulsar()

    def stop(self):
        self.moduleStateHandler.requestStateChange(self.moduleStates.HARDWARECOMMUNICATION.STOPPED)
        self.stopPulsar()

    def _close(self):
        self.window.close()

    def handlemasterstate(self, state):
        """ 
        Handle the state transition by updating the status label and have the
        GUI reflect the possibilities of the current state.
        """

        try:
            #stateAsState = self.states.getState(state) # ensure we have the State object (not the int)
            stateAsState = self.masterStateHandler.getState(state) # ensure we have the State object (not the int)
            
            # emergency stop
            if stateAsState == self.moduleStates.ERROR:
                self._stop()

            # update the state label
            self.widget.lblState.setText(str(stateAsState))
            self.widget.repaint()

        except Exception as inst:
            print (inst)

    def handlemodulestate(self, state):
        """ 
        Handle the state transition by updating the status label and have the
        GUI reflect the possibilities of the current state.
        """

        try:
            #stateAsState = self.states.getState(state) # ensure we have the State object (not the int)
            stateAsState = self.moduleStateHandler.getState(state) # ensure we have the State object (not the int)
            
            # emergency stop
            if stateAsState == self.moduleStates.ERROR:
                self._stop()

            # update the state label
            self.stateWidget.lblModulestate.setText(str(stateAsState.name))
            self.stateWidget.repaint()

            if stateAsState == self.moduleStates.HARDWARECOMMUNICATION.RUNNING:
                self.stateWidget.btnStart.setStyleSheet("background-color: green")
            else:
                self.stateWidget.btnStart.setStyleSheet("background-color: none")

        except Exception as inst:
            print (inst)