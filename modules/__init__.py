''' relative import used by sibling packages
    action classes, belonging to widgets (within the same module directory) are imported in the widget-class
'''

from .datarecorder.widget.datarecorder import DatarecorderWidget
from .hardwarecommunication.widget.hardwarecommunication import HardwarecommunicationWidget
from .feedbackcontroller.widget.feedbackcontroller import FeedbackcontrollerWidget
from .carlainterface.widget.carlainterface import CarlainterfaceWidget
from .trajectoryrecorder.widget.trajectoryrecorder import TrajectoryrecorderWidget
