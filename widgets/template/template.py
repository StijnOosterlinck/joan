from process import Control
from PyQt5 import QtCore
import os

class TemplateWidget(Control):
    def __init__(self, *args, **kwargs):
        kwargs['millis'] = 'millis' in kwargs.keys() and kwargs['millis'] or 20
        kwargs['callback'] = [self.do]  # method will run each given millis

        kwargs['ui'] = os.path.join(os.path.dirname(os.path.realpath(__file__)),"template.ui")
        Control.__init__(self, *args, **kwargs)

        self.statehandler.stateChanged.connect(self.handlestate)

    # callback class is called each time a pulse has come from the Pulsar class instance
    def do(self):
        pass

    @QtCore.pyqtSlot(str)
    def setmillis(self, millis):
        try:
            millis = int(millis)
            self.setInterval(millis)
        except:
            pass

    def start(self):
        print(self.widget.windowTitle())
        self.widget.setWindowTitle("Template title")
        self.widget.show()
        self.startPulsar()

    def stop(self):
        self.stopPulsar()

    def close(self):
        self.widget.close()

    def handlestate(self, state):
        """ 
        Handle the state transition by updating the status label and have the
        GUI reflect the possibilities of the current state.
        """

        try:
            stateAsState = self.states.getState(state) # ensure we have the State object (not the int)
            
            # emergency stop
            if stateAsState == self.states.ERROR:
                self.stop()

            # update the state label
            self.widget.lblState.setText(str(stateAsState))

        except Exception as inst:
            print (inst)